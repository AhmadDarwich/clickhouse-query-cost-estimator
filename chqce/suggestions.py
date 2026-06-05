from dataclasses import dataclass
from typing import List, Set

import sqlglot
import sqlglot.expressions as exp


@dataclass
class IndexSuggestion:
    table: str
    column: str
    reason: str
    suggestion: str
    in_primary_key: bool = False


def _parse_query(query: str):
    """Return (tables, where_cols) — tolerates parse failures."""
    try:
        tree = sqlglot.parse_one(query, read="clickhouse")
    except Exception:
        try:
            tree = sqlglot.parse_one(query)
        except Exception:
            return {}, {}

    # alias/name -> (database, table_name)
    tables: dict[str, tuple[str, str]] = {}
    for node in tree.find_all(exp.Table):
        if not node.name:
            continue
        alias = (node.alias or node.name).lower()
        tables[alias] = (node.db or "", node.name)

    # column_name -> set of condition kinds
    where_cols: dict[str, set] = {}

    def _add(col_node: exp.Column, kind: str):
        if col_node.name:
            where_cols.setdefault(col_node.name.lower(), set()).add(kind)

    where = tree.find(exp.Where)
    if where:
        for node in where.find_all(exp.EQ):
            for c in node.find_all(exp.Column):
                _add(c, "equality")
        for node in where.find_all(exp.Between):
            for c in node.find_all(exp.Column):
                _add(c, "range")
        for node in where.find_all(exp.LT, exp.LTE, exp.GT, exp.GTE):
            for c in node.find_all(exp.Column):
                _add(c, "range")
        for node in where.find_all(exp.Like, exp.ILike):
            for c in node.find_all(exp.Column):
                _add(c, "like")
        for node in where.find_all(exp.In):
            for c in node.find_all(exp.Column):
                _add(c, "in")

    return tables, where_cols


def _get_order_by_cols(client, database: str, table: str) -> List[str]:
    try:
        res = client.query(
            "SELECT sorting_key, primary_key FROM system.tables "
            "WHERE database = {db:String} AND name = {t:String}",
            parameters={"db": database, "t": table},
        )
        if not res.result_rows:
            return []
        sorting_key, primary_key = res.result_rows[0]
        key = sorting_key or primary_key
        if key:
            return [c.strip() for c in key.split(",") if c.strip()]
    except Exception:
        pass
    return []


def _get_col_type(client, database: str, table: str, column: str) -> str:
    try:
        res = client.query(
            "SELECT type FROM system.columns "
            "WHERE database={db:String} AND table={t:String} AND name={c:String}",
            parameters={"db": database, "t": table, "c": column},
        )
        if res.result_rows:
            return res.result_rows[0][0]
    except Exception:
        pass
    return ""


def _best_index_type(col_type: str, conditions: Set[str]) -> str:
    ct = col_type.lower()
    if "like" in conditions:
        return "tokenbf_v1(32768, 3, 0)"
    if "range" in conditions:
        return "minmax"
    if "string" in ct or "fixedstring" in ct:
        return "bloom_filter(0.01)"
    if any(x in ct for x in ("int", "uint", "float", "decimal", "date", "datetime")):
        return "set(100)" if "in" in conditions or "equality" in conditions else "minmax"
    return "bloom_filter(0.01)"


def get_index_suggestions(
    query: str, client, current_database: str = "default"
) -> List[IndexSuggestion]:
    tables, where_cols = _parse_query(query)
    if not where_cols or not tables:
        return []

    suggestions: List[IndexSuggestion] = []

    for _alias, (db, table_name) in tables.items():
        effective_db = db or current_database
        pk_cols = _get_order_by_cols(client, effective_db, table_name)
        pk_lower = {c.lower() for c in pk_cols}
        full_table = f"{effective_db}.{table_name}" if effective_db else table_name

        for col_name, conditions in where_cols.items():
            in_pk = col_name in pk_lower

            if in_pk:
                suggestions.append(
                    IndexSuggestion(
                        table=full_table,
                        column=col_name,
                        reason=f"already in ORDER BY {pk_cols}",
                        suggestion="",
                        in_primary_key=True,
                    )
                )
            else:
                col_type = _get_col_type(client, effective_db, table_name, col_name)
                idx_type = _best_index_type(col_type, conditions)
                idx_name = f"idx_{table_name}_{col_name}"
                alter_sql = (
                    f"ALTER TABLE {full_table}\n"
                    f"    ADD INDEX {idx_name} {col_name}\n"
                    f"    TYPE {idx_type} GRANULARITY 4;"
                )
                pk_label = pk_cols if pk_cols else ["(unknown)"]
                suggestions.append(
                    IndexSuggestion(
                        table=full_table,
                        column=col_name,
                        reason=f"not in ORDER BY {pk_label}",
                        suggestion=alter_sql,
                        in_primary_key=False,
                    )
                )

    return suggestions
