import sys

import click
from rich.console import Console

from . import __version__
from .connection import create_client, test_connection
from .estimator import QueryEstimator
from .formatter import console, print_header, print_result
from .suggestions import get_index_suggestions

_err = Console(stderr=True)


def _collect_interactive() -> str:
    """Collect a multi-line SQL query from stdin.

    Submit by ending a line with ';' or typing GO on its own line.
    """
    console.print(
        "\n[dim]Paste or type your SQL query."
        "  End with [bold];[/bold] or type [bold]GO[/bold] on its own line."
        "  [bold]Ctrl+C[/bold] to exit.[/dim]\n"
    )
    lines: list[str] = []
    try:
        while True:
            prefix = "[bold cyan]SQL>[/bold cyan] " if not lines else "     [dim]>[/dim] "
            console.print(prefix, end="")
            try:
                line = input()
            except EOFError:
                break
            stripped = line.strip()
            if stripped.upper() == "GO" or stripped == ";":
                if lines:
                    break
                continue
            lines.append(line)
            if stripped.endswith(";"):
                break
    except KeyboardInterrupt:
        console.print("\n[dim]Bye![/dim]")
        sys.exit(0)

    return "\n".join(lines).strip()


def _run(query: str, estimator: QueryEstimator, client, database: str, execute: bool) -> None:
    with console.status("[bold green]Analyzing…[/bold green]", spinner="dots"):
        result = estimator.estimate(query, execute=execute)
        suggestions = get_index_suggestions(query, client, current_database=database)
    print_result(result, suggestions)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("query", required=False)
@click.option("--host", "-H", default="localhost", envvar="CLICKHOUSE_HOST",
              show_default=True, help="ClickHouse host")
@click.option("--port", "-p", default=8123, envvar="CLICKHOUSE_PORT", type=int,
              show_default=True, help="HTTP(S) port")
@click.option("--user", "-u", default="default", envvar="CLICKHOUSE_USER",
              show_default=True, help="Username")
@click.option("--password", "-P", default="", envvar="CLICKHOUSE_PASSWORD",
              help="Password (or set CLICKHOUSE_PASSWORD)")
@click.option("--database", "-d", default="default", envvar="CLICKHOUSE_DATABASE",
              show_default=True, help="Default database")
@click.option("--no-execute", is_flag=True, default=False,
              help="Estimate only — do not actually run the query")
@click.version_option(__version__, "-V", "--version")
def cli(query, host, port, user, password, database, no_execute):
    """ClickHouse Query Cost Estimator.

    Estimates rows scanned, memory usage, and execution time for a ClickHouse
    SQL query, and suggests indexes based on WHERE-clause columns.

    Pass QUERY directly, or omit it to enter interactive mode.

    \b
    Environment variables (override defaults):
      CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_USER,
      CLICKHOUSE_PASSWORD, CLICKHOUSE_DATABASE

    \b
    Examples:
      chqce "SELECT count() FROM hits WHERE EventDate = today()"
      chqce --host my.ch.host --database analytics --no-execute
    """
    try:
        client = create_client(host=host, port=port, user=user,
                               password=password, database=database)
        ok, version_or_err = test_connection(client)
    except Exception as e:
        _err.print(f"[red]Connection error:[/red] {e}")
        sys.exit(1)

    if not ok:
        _err.print(f"[red]Connection failed:[/red] {version_or_err}")
        sys.exit(1)

    print_header(version_or_err, host, port, database)

    estimator = QueryEstimator(client)
    execute = not no_execute

    if query:
        _run(query, estimator, client, database, execute)
    else:
        while True:
            q = _collect_interactive()
            if not q:
                continue
            _run(q, estimator, client, database, execute)
            console.print("[dim]" + "─" * 60 + "[/dim]")
