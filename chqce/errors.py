"""Classify ClickHouse / client errors into actionable hints.

ClickHouse surfaces resource limits as server errors (timeout, AST too big,
memory, query size). We map the raw message to a short category and a hint
that tells the user which flag or setting can get them unstuck.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ClassifiedError:
    category: str            # machine-readable bucket
    title: str               # short human label
    hint: Optional[str]      # actionable suggestion, or None


# Each rule: (category, title, list-of-substrings-to-match, hint)
# Substring match is case-insensitive. Order matters — first match wins.
_RULES = [
    (
        "timeout",
        "Query timed out",
        ["timeout_exceeded", "timeout exceeded", "max_execution_time",
         "timed out", "read timed out", "readtimeout"],
        "The query exceeded its time budget. Try:\n"
        "  • raise the limit:  --timeout 600  (seconds, 0 = unlimited)\n"
        "  • estimate without running:  --no-execute\n"
        "  • narrow the query with a WHERE filter or LIMIT",
    ),
    (
        "ast_too_big",
        "Query AST is too big",
        ["too_big_ast", "ast is too big", "max_ast_elements",
         "max_expanded_ast_elements"],
        "The parsed query has too many elements (often huge IN-lists or "
        "deeply nested expressions). Try:\n"
        "  • raise the limit:  --max-ast-elements 500000\n"
        "  • replace a long  IN (1, 2, 3, …)  with a subquery or a "
        "temporary table / JOIN",
    ),
    (
        "parser_depth",
        "Query nesting is too deep",
        ["too_deep_recursion", "maximum parse depth", "max_parser_depth"],
        "The query nests deeper than the parser allows. Try:\n"
        "  • flatten deeply nested subqueries or boolean expressions\n"
        "  • raise the server setting  max_parser_depth",
    ),
    (
        "query_size",
        "Query text is too large",
        ["max query size exceeded", "max_query_size"],
        "The raw query exceeds ClickHouse's max_query_size (256 KiB default). "
        "Try:\n"
        "  • raise the limit:  --max-query-size 1048576  (bytes)",
    ),
    (
        "memory",
        "Query ran out of memory",
        ["memory_limit_exceeded", "memory limit", "max_memory_usage"],
        "The query exceeded the memory budget. Try:\n"
        "  • add a WHERE filter or LIMIT to scan less data\n"
        "  • pre-aggregate, or raise the server setting  max_memory_usage",
    ),
    (
        "read_limit",
        "Query scans too much data",
        ["too_many_rows", "max_rows_to_read", "too_many_bytes",
         "max_bytes_to_read"],
        "The query would read more rows/bytes than allowed. Try:\n"
        "  • add a WHERE filter on the table's ORDER BY columns\n"
        "  • check the Index Suggestions below",
    ),
]


def classify_error(message: Optional[str]) -> Optional[ClassifiedError]:
    """Return a ClassifiedError for a known failure, or None if unrecognized."""
    if not message:
        return None
    low = message.lower()
    for category, title, needles, hint in _RULES:
        if any(n in low for n in needles):
            return ClassifiedError(category=category, title=title, hint=hint)
    return None
