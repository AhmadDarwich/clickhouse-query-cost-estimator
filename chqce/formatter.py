from typing import List

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .estimator import EstimateResult
from .suggestions import IndexSuggestion

console = Console()


# ── helpers ─────────────────────────────────────────────────────────────────

def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return "—"
    for unit, threshold in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= threshold:
            return f"{n / threshold:.1f} {unit}"
    return f"{n} B"


def _fmt_rows(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_ms(ms: float) -> str:
    if ms <= 0:
        return "—"
    if ms >= 1_000:
        return f"{ms / 1_000:.2f} s"
    if ms >= 1:
        return f"{ms:.1f} ms"
    return f"{ms * 1_000:.0f} µs"


# ── public API ───────────────────────────────────────────────────────────────

def print_header(version: str, host: str, port: int, database: str) -> None:
    console.print()
    console.print(
        Panel(
            f"[bold cyan]ClickHouse Query Cost Estimator[/bold cyan]  [dim]v0.1.0[/dim]\n"
            f"[dim]Connected to [green]{host}:{port}[/green]"
            f"  ·  database: [green]{database}[/green]"
            f"  ·  ClickHouse [green]{version}[/green][/dim]",
            box=box.ROUNDED,
            border_style="cyan",
        )
    )


def print_result(result: EstimateResult, suggestions: List[IndexSuggestion]) -> None:
    console.print()

    # ── Query display ────────────────────────────────────────────────────────
    # Truncate the echo for huge queries so results stay visible.
    QUERY_ECHO_LINES = 30
    q = result.query.strip()
    q_lines = q.split("\n")
    if len(q_lines) > QUERY_ECHO_LINES:
        head = "\n".join(q_lines[:QUERY_ECHO_LINES])
        body = Syntax(head, "sql", theme="monokai")
        title = (
            f"[bold]Query[/bold]  "
            f"[dim](showing {QUERY_ECHO_LINES} of {len(q_lines)} lines, "
            f"{len(q):,} chars)[/dim]"
        )
    else:
        body = Syntax(q, "sql", theme="monokai")
        title = "[bold]Query[/bold]"
    console.print(Panel(body, title=title, border_style="blue"))
    console.print()

    # ── Errors ───────────────────────────────────────────────────────────────
    if result.explain_error:
        console.print(f"[yellow]⚠  Estimate unavailable:[/yellow] {result.explain_error}\n")
    if result.execution_error:
        console.print(f"[red]✗  Execution error:[/red] {result.execution_error}\n")
        _print_index_suggestions(suggestions)
        return

    # ── Cost estimate ────────────────────────────────────────────────────────
    if result.table_estimates:
        t = Table(
            title="[bold]Cost Estimate  [dim](from EXPLAIN ESTIMATE)[/dim][/bold]",
            box=box.SIMPLE_HEAD,
            header_style="bold magenta",
        )
        t.add_column("Database", style="cyan")
        t.add_column("Table", style="cyan")
        t.add_column("Parts", justify="right")
        t.add_column("Est. Rows", justify="right", style="yellow")
        t.add_column("Marks", justify="right")

        for te in result.table_estimates:
            t.add_row(te.database, te.table, str(te.parts), _fmt_rows(te.rows), str(te.marks))

        if len(result.table_estimates) > 1:
            t.add_section()
            t.add_row(
                "[bold]Total[/bold]",
                "",
                f"[bold]{result.total_parts}[/bold]",
                f"[bold yellow]{_fmt_rows(result.total_rows)}[/bold yellow]",
                f"[bold]{result.total_marks}[/bold]",
            )
        console.print(t)
        console.print()

    # ── Timing ───────────────────────────────────────────────────────────────
    t = Table(
        title="[bold]Timing[/bold]",
        box=box.SIMPLE_HEAD,
        header_style="bold magenta",
    )
    t.add_column("Phase", style="cyan")
    t.add_column("Time", justify="right", style="green")
    t.add_column("Notes", style="dim")

    if result.explain_time_ms > 0:
        t.add_row(
            "SQL Analyzer  (EXPLAIN)",
            _fmt_ms(result.explain_time_ms),
            "parsing + plan generation",
        )
    if result.was_executed:
        t.add_row(
            "Execution  (client)",
            _fmt_ms(result.execution_time_ms),
            "wall-clock including network",
        )
        if result.server_time_ms > 0:
            t.add_row(
                "Execution  (server)",
                _fmt_ms(result.server_time_ms),
                "server-side only",
            )

    console.print(t)
    console.print()

    # ── Execution stats ───────────────────────────────────────────────────────
    if result.was_executed:
        t = Table(
            title="[bold]Execution Stats[/bold]",
            box=box.SIMPLE_HEAD,
            header_style="bold magenta",
        )
        t.add_column("Metric", style="cyan")
        t.add_column("Value", justify="right", style="green")

        t.add_row("Rows read", _fmt_rows(result.read_rows))
        t.add_row("Bytes read", _fmt_bytes(result.read_bytes))
        t.add_row("Result rows", _fmt_rows(result.result_rows))
        t.add_row("Result size", _fmt_bytes(result.result_bytes))
        t.add_row("Peak memory", _fmt_bytes(result.memory_usage_bytes))

        console.print(t)
        console.print()

    # ── Query plan ────────────────────────────────────────────────────────────
    if result.query_plan:
        lines = result.query_plan.split("\n")
        body = "\n".join(lines[:40])
        if len(lines) > 40:
            body += f"\n[dim]… {len(lines) - 40} more lines[/dim]"
        console.print(
            Panel(body, title="[bold]Query Plan[/bold]", border_style="dim", expand=False)
        )
        console.print()

    # ── Index suggestions ─────────────────────────────────────────────────────
    _print_index_suggestions(suggestions)


def _print_index_suggestions(suggestions: List[IndexSuggestion]) -> None:
    if not suggestions:
        console.print("[dim]No index suggestions — add a WHERE clause to get recommendations.[/dim]")
        console.print()
        return

    console.rule("[bold]Index Suggestions[/bold]", style="magenta")
    console.print()

    for s in suggestions:
        if s.in_primary_key:
            console.print(
                f"  [green]✓[/green]  [bold]{s.column}[/bold]"
                f"  [dim]on {s.table}[/dim]  —  {s.reason}"
            )
        else:
            console.print(
                f"  [yellow]⚠[/yellow]  [bold]{s.column}[/bold]"
                f"  [dim]on {s.table}[/dim]  —  {s.reason}"
            )
            if s.suggestion:
                console.print(
                    Syntax(s.suggestion, "sql", theme="monokai", padding=(0, 4))
                )
        console.print()
