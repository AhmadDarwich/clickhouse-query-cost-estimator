from conftest import FakeResult

from chqce.estimator import QueryEstimator


def test_is_select():
    assert QueryEstimator._is_select("SELECT 1")
    assert QueryEstimator._is_select("  select 1")
    assert QueryEstimator._is_select("WITH x AS (SELECT 1) SELECT * FROM x")
    assert not QueryEstimator._is_select("INSERT INTO t VALUES (1)")
    assert not QueryEstimator._is_select("")


def test_estimate_success(make_client):
    exec_result = FakeResult(
        rows=[[1], [2]],
        summary={
            "read_rows": "1000",
            "read_bytes": "2048",
            "result_bytes": "16",
            "elapsed_ns": "5000000",  # 5 ms
        },
        query_id="qid-1",
    )
    client = make_client(
        estimate_rows=[["default", "hits", 4, 1000, 50]],
        plan_rows=[["Expression"], ["ReadFromMergeTree (default.hits)"]],
        exec_result=exec_result,
        memory=123456,
    )
    result = QueryEstimator(client).estimate("SELECT count() FROM hits", execute=True)

    assert len(result.table_estimates) == 1
    te = result.table_estimates[0]
    assert (te.database, te.table, te.parts, te.rows, te.marks) == ("default", "hits", 4, 1000, 50)
    assert result.total_rows == 1000
    assert result.total_parts == 4
    assert result.total_marks == 50

    assert "ReadFromMergeTree" in result.query_plan
    assert result.explain_time_ms >= 0

    assert result.was_executed is True
    assert result.result_rows == 2
    assert result.read_rows == 1000
    assert result.read_bytes == 2048
    assert result.result_bytes == 16
    assert result.server_time_ms == 5.0
    assert result.memory_usage_bytes == 123456
    assert result.execution_error is None


def test_estimate_aggregates_multiple_tables(make_client):
    client = make_client(
        estimate_rows=[
            ["default", "a", 2, 100, 10],
            ["default", "b", 3, 200, 20],
        ],
        exec_result=FakeResult(rows=[], summary={}, query_id=None),
    )
    result = QueryEstimator(client).estimate(
        "SELECT * FROM a JOIN b ON a.id = b.id", execute=True
    )
    assert len(result.table_estimates) == 2
    assert result.total_rows == 300
    assert result.total_parts == 5
    assert result.total_marks == 30


def test_estimate_no_execute_skips_execution(make_client):
    client = make_client(estimate_rows=[["default", "hits", 1, 10, 1]])
    result = QueryEstimator(client).estimate("SELECT 1 FROM hits", execute=False)

    assert result.was_executed is False
    assert result.execution_error is None
    assert result.table_estimates  # estimate still ran
    # No actual query / memory lookup should have happened.
    assert all("system.query_log" not in sql.lower() for sql, _ in client.calls)


def test_estimate_explain_error_is_captured(make_client):
    client = make_client(raise_on={"EXPLAIN ESTIMATE": RuntimeError("boom-estimate")})
    result = QueryEstimator(client).estimate("SELECT 1 FROM hits", execute=False)

    assert result.explain_error == "boom-estimate"
    assert result.table_estimates == []


def test_estimate_execution_error_is_captured(make_client):
    client = make_client(
        estimate_rows=[["default", "hits", 1, 10, 1]],
        raise_on_exec=RuntimeError("boom-exec"),
    )
    result = QueryEstimator(client).estimate(
        "SELECT * FROM hits WHERE x = 1", execute=True
    )
    assert result.execution_error == "boom-exec"
    assert result.was_executed is False
    # The estimate step still populated despite the execution failure.
    assert result.total_rows == 10


def test_estimate_non_select_skips_explain(make_client):
    client = make_client(exec_result=FakeResult(rows=[], summary={}, query_id=None))
    result = QueryEstimator(client).estimate("INSERT INTO t VALUES (1)", execute=True)

    assert result.table_estimates == []
    assert result.explain_error is None
    # No EXPLAIN calls were issued for a non-SELECT.
    assert all(not sql.upper().startswith("EXPLAIN") for sql, _ in client.calls)
