import io

from rich.console import Console

import chqce.formatter as formatter
from chqce.formatter import _fmt_bytes, _fmt_ms, _fmt_rows
from chqce.estimator import EstimateResult


# ── number formatting ────────────────────────────────────────────────────────

def test_fmt_bytes():
    assert _fmt_bytes(0) == "—"
    assert _fmt_bytes(-5) == "—"
    assert _fmt_bytes(512) == "512 B"
    assert _fmt_bytes(1536) == "1.5 KB"
    assert _fmt_bytes(1 << 20) == "1.0 MB"
    assert _fmt_bytes(1 << 30) == "1.0 GB"


def test_fmt_rows():
    assert _fmt_rows(999) == "999"
    assert _fmt_rows(1000) == "1.0K"
    assert _fmt_rows(2_500_000) == "2.5M"
    assert _fmt_rows(3_000_000_000) == "3.0B"


def test_fmt_ms():
    assert _fmt_ms(0) == "—"
    assert _fmt_ms(0.5) == "500 µs"
    assert _fmt_ms(12.3) == "12.3 ms"
    assert _fmt_ms(1500) == "1.50 s"


# ── print_result rendering ───────────────────────────────────────────────────

def _render(monkeypatch, result, suggestions):
    buf = io.StringIO()
    test_console = Console(file=buf, width=140, force_terminal=False, color_system=None)
    monkeypatch.setattr(formatter, "console", test_console)
    formatter.print_result(result, suggestions)
    return buf.getvalue()


def test_print_result_truncates_huge_query(monkeypatch):
    query = "\n".join(f"SELECT col_{i}" for i in range(50))
    result = EstimateResult(query=query)
    result.explain_error = "skip the rest"  # short-circuit; we only test the echo
    out = _render(monkeypatch, result, [])
    assert "showing 30 of 50 lines" in out


def test_print_result_does_not_truncate_small_query(monkeypatch):
    result = EstimateResult(query="SELECT 1")
    result.explain_error = "skip"
    out = _render(monkeypatch, result, [])
    assert "showing" not in out


def test_print_result_renders_classified_error_hint(monkeypatch):
    result = EstimateResult(query="SELECT * FROM t")
    result.execution_error = (
        "Code: 159. DB::Exception: Timeout exceeded (TIMEOUT_EXCEEDED)"
    )
    out = _render(monkeypatch, result, [])
    assert "Query timed out" in out
    assert "--timeout" in out


def test_print_result_shows_execution_stats(monkeypatch):
    result = EstimateResult(query="SELECT 1")
    result.was_executed = True
    result.read_rows = 1000
    result.read_bytes = 2048
    result.memory_usage_bytes = 1 << 20
    out = _render(monkeypatch, result, [])
    assert "Execution Stats" in out
    assert "Rows read" in out
    assert "Peak memory" in out
