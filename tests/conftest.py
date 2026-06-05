"""Shared test fixtures: a fake ClickHouse client so tests need no real server."""

from typing import Callable, Optional

import pytest


class FakeResult:
    """Stand-in for a clickhouse-connect QueryResult."""

    def __init__(self, rows=None, summary=None, query_id=None):
        self.result_rows = rows if rows is not None else []
        self.summary = summary if summary is not None else {}
        self.query_id = query_id


class FakeClient:
    """Routes .query() calls to a handler and records every call.

    The handler receives (sql, parameters) and returns a FakeResult, or
    raises an Exception to simulate a server error.
    """

    def __init__(self, handler: Callable[[str, Optional[dict]], FakeResult]):
        self._handler = handler
        self.calls = []  # list of (sql, parameters)

    def query(self, sql, parameters=None):
        self.calls.append((sql, parameters))
        return self._handler(sql, parameters)


def make_handler(
    *,
    estimate_rows=None,
    plan_rows=None,
    exec_result: Optional[FakeResult] = None,
    memory=None,
    sorting_key="",
    primary_key="",
    col_type=None,
    version="23.8.1.1",
    raise_on: Optional[dict] = None,
    raise_on_exec: Optional[Exception] = None,
):
    """Build a handler that routes by SQL shape.

    `raise_on` maps an uppercase substring to an Exception, raised whenever the
    SQL matches (useful for EXPLAIN-prefixed queries, which are unique).
    `raise_on_exec` raises only for the actual user query — handy because the
    query body also appears inside the EXPLAIN-prefixed variants.
    """
    raise_on = raise_on or {}

    def handler(sql, parameters=None):
        up = sql.strip().upper()
        for needle, exc in raise_on.items():
            if needle.upper() in up:
                raise exc

        if up.startswith("EXPLAIN ESTIMATE"):
            return FakeResult(estimate_rows or [])
        if up.startswith("EXPLAIN PLAN"):
            return FakeResult(plan_rows or [])
        if "SELECT VERSION()" in up:
            return FakeResult([[version]])
        if "MEMORY_USAGE" in up and "QUERY_LOG" in up:
            return FakeResult([[memory]] if memory is not None else [])
        if "SYSTEM.TABLES" in up:
            return FakeResult([[sorting_key, primary_key]])
        if "SYSTEM.COLUMNS" in up:
            return FakeResult([[col_type]] if col_type is not None else [])
        # The actual user query.
        if raise_on_exec is not None:
            raise raise_on_exec
        return exec_result if exec_result is not None else FakeResult([[1]])

    return handler


@pytest.fixture
def fake_result_cls():
    return FakeResult


@pytest.fixture
def make_client():
    """Returns a factory: pass make_handler(...) kwargs, get a FakeClient."""
    def _factory(**kwargs):
        return FakeClient(make_handler(**kwargs))
    return _factory
