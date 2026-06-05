import io

import pytest
from click.testing import CliRunner

import chqce.cli as cli_module
from chqce.cli import _resolve_query, cli
from conftest import FakeClient, make_handler


# ── _resolve_query priority ──────────────────────────────────────────────────

def test_resolve_query_prefers_file(tmp_path):
    f = tmp_path / "q.sql"
    f.write_text("SELECT from_file\n")
    assert _resolve_query("SELECT from_arg", str(f)) == "SELECT from_file"


def test_resolve_query_uses_arg_when_no_file():
    assert _resolve_query("SELECT from_arg", None) == "SELECT from_arg"


def test_resolve_query_reads_stdin_when_piped(monkeypatch):
    fake_stdin = io.StringIO("SELECT from_stdin\n")
    fake_stdin.isatty = lambda: False
    monkeypatch.setattr("sys.stdin", fake_stdin)
    assert _resolve_query(None, None) == "SELECT from_stdin"


def test_resolve_query_returns_none_for_interactive(monkeypatch):
    fake_stdin = io.StringIO("")
    fake_stdin.isatty = lambda: True
    monkeypatch.setattr("sys.stdin", fake_stdin)
    assert _resolve_query(None, None) is None


# ── full CLI via CliRunner ───────────────────────────────────────────────────

@pytest.fixture
def patched_client(monkeypatch):
    """Patch create_client/test_connection so the CLI needs no real server."""
    client = FakeClient(
        make_handler(
            estimate_rows=[["default", "hits", 2, 500, 25]],
            plan_rows=[["ReadFromMergeTree (default.hits)"]],
            sorting_key="id",
            col_type="UInt64",
            version="23.8.1.1",
        )
    )
    monkeypatch.setattr(cli_module, "create_client", lambda **kw: client)
    monkeypatch.setattr(cli_module, "test_connection", lambda c: (True, "23.8.1.1"))
    return client


def test_cli_runs_query_argument(patched_client):
    runner = CliRunner()
    result = runner.invoke(cli, ["SELECT count() FROM hits WHERE user_id = 1"])
    assert result.exit_code == 0
    assert "Cost Estimate" in result.output
    assert "Index Suggestions" in result.output


def test_cli_no_execute_flag(patched_client):
    runner = CliRunner()
    result = runner.invoke(cli, ["--no-execute", "SELECT 1 FROM hits"])
    assert result.exit_code == 0
    # Execution stats only appear when the query actually runs.
    assert "Execution Stats" not in result.output


def test_cli_reads_from_file(patched_client, tmp_path):
    f = tmp_path / "q.sql"
    f.write_text("SELECT count() FROM hits WHERE user_id = 1")
    runner = CliRunner()
    result = runner.invoke(cli, ["-f", str(f)])
    assert result.exit_code == 0
    assert "Cost Estimate" in result.output


def test_cli_missing_file_errors():
    runner = CliRunner()
    result = runner.invoke(cli, ["-f", "/nonexistent/path.sql"])
    assert result.exit_code != 0


def test_cli_connection_failure_exits_nonzero(monkeypatch):
    monkeypatch.setattr(cli_module, "create_client", lambda **kw: object())
    monkeypatch.setattr(cli_module, "test_connection", lambda c: (False, "no route to host"))
    runner = CliRunner()
    result = runner.invoke(cli, ["SELECT 1"])
    assert result.exit_code == 1
    # The error goes to stderr, which Click may capture separately.
    try:
        combined = result.output + (result.stderr or "")
    except ValueError:
        combined = result.output
    assert "Connection failed" in combined


def test_cli_help_lists_flags():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for flag in ["--file", "--timeout", "--max-query-size", "--max-ast-elements", "--no-execute"]:
        assert flag in result.output
