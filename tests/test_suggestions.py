from chqce.suggestions import (
    _best_index_type,
    _parse_query,
    get_index_suggestions,
)


# ── _parse_query ─────────────────────────────────────────────────────────────

def test_parse_query_extracts_table_and_columns():
    tables, where_cols = _parse_query(
        "SELECT * FROM orders WHERE user_id = 5 AND created_at > '2020-01-01'"
    )
    assert ("", "orders") in tables.values()
    assert "user_id" in where_cols
    assert "created_at" in where_cols


def test_parse_query_condition_kinds():
    _, eq = _parse_query("SELECT 1 FROM t WHERE a = 1")
    assert eq["a"] == {"equality"}

    _, rng = _parse_query("SELECT 1 FROM t WHERE a > 1")
    assert "range" in rng["a"]

    _, btw = _parse_query("SELECT 1 FROM t WHERE a BETWEEN 1 AND 2")
    assert "range" in btw["a"]

    _, like = _parse_query("SELECT 1 FROM t WHERE a LIKE '%x%'")
    assert "like" in like["a"]

    _, in_ = _parse_query("SELECT 1 FROM t WHERE a IN (1, 2, 3)")
    assert "in" in in_["a"]


def test_parse_query_resolves_alias():
    tables, _ = _parse_query("SELECT * FROM orders AS o WHERE o.user_id = 5")
    assert tables["o"] == ("", "orders")


def test_parse_query_no_where_returns_empty_cols():
    _, where_cols = _parse_query("SELECT * FROM orders")
    assert where_cols == {}


def test_parse_query_handles_unparseable_input():
    tables, where_cols = _parse_query("this is not valid sql ((((")
    assert tables == {}
    assert where_cols == {}


# ── _best_index_type ─────────────────────────────────────────────────────────

def test_best_index_type_like_uses_tokenbf():
    assert _best_index_type("String", {"like"}).startswith("tokenbf")


def test_best_index_type_range_uses_minmax():
    assert _best_index_type("DateTime", {"range"}) == "minmax"


def test_best_index_type_string_equality_uses_bloom():
    assert _best_index_type("String", {"equality"}).startswith("bloom_filter")


def test_best_index_type_numeric_equality_uses_set():
    assert _best_index_type("UInt64", {"equality"}) == "set(100)"
    assert _best_index_type("Int32", {"in"}) == "set(100)"


def test_best_index_type_numeric_range_uses_minmax():
    assert _best_index_type("UInt64", {"range"}) == "minmax"


# ── get_index_suggestions ────────────────────────────────────────────────────

def test_suggestion_for_column_not_in_sort_key(make_client):
    client = make_client(sorting_key="id", col_type="UInt64")
    suggestions = get_index_suggestions(
        "SELECT * FROM orders WHERE user_id = 5", client, current_database="default"
    )
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.column == "user_id"
    assert s.in_primary_key is False
    assert s.table == "default.orders"
    assert "ADD INDEX idx_orders_user_id user_id" in s.suggestion
    assert "TYPE set(100)" in s.suggestion


def test_column_already_in_sort_key_is_flagged(make_client):
    client = make_client(sorting_key="id", col_type="UInt64")
    suggestions = get_index_suggestions(
        "SELECT * FROM orders WHERE id = 5", client, current_database="default"
    )
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.column == "id"
    assert s.in_primary_key is True
    assert s.suggestion == ""


def test_no_where_clause_yields_no_suggestions(make_client):
    client = make_client(sorting_key="id")
    suggestions = get_index_suggestions("SELECT * FROM orders", client)
    assert suggestions == []


def test_string_column_suggests_bloom_filter(make_client):
    client = make_client(sorting_key="id", col_type="String")
    suggestions = get_index_suggestions(
        "SELECT * FROM orders WHERE email = 'a@b.com'", client
    )
    assert "TYPE bloom_filter" in suggestions[0].suggestion
