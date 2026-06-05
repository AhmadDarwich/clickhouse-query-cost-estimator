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


def _resolve_query(query: str | None, file: str | None) -> str | None:
    """Determine the query source, in priority order.

    1. --file FILE          read the query from a file (best for huge queries)
    2. QUERY argument       passed directly on the command line
    3. piped stdin          e.g.  `chqce < query.sql`  or  `cat q.sql | chqce`
    4. None                 -> caller falls back to interactive mode
    """
    if file:
        with open(file, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    if query:
        return query
    # Query piped in on stdin (non-interactive).
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return data
    return None


def _run(query: str, estimator: QueryEstimator, client, database: str, execute: bool) -> None:
    with console.status("[bold green]Analyzing…[/bold green]", spinner="dots"):
        result = estimator.estimate(query, execute=execute)
        suggestions = get_index_suggestions(query, client, current_database=database)
    print_result(result, suggestions)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("query", required=False)
@click.option("--file", "-f", "file", type=click.Path(exists=True, dir_okay=False),
              default=None, help="Read the query from a file (best for huge queries)")
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
@click.option("--max-query-size", default=0, type=int, metavar="BYTES",
              help="Raise ClickHouse max_query_size for very large queries "
                   "(server default is 262144)")
@click.option("--timeout", "-t", default=0, type=int, metavar="SECONDS",
              help="Server-side max_execution_time; query is aborted after this "
                   "many seconds (0 = unlimited)")
@click.option("--max-ast-elements", default=0, type=int, metavar="N",
              help="Raise ClickHouse max_ast_elements for queries that fail with "
                   "'AST is too big' (server default is 50000)")
@click.option("--no-execute", is_flag=True, default=False,
              help="Estimate only — do not actually run the query")
@click.version_option(__version__, "-V", "--version")
def cli(query, file, host, port, user, password, database, max_query_size,
        timeout, max_ast_elements, no_execute):
    """ClickHouse Query Cost Estimator.

    Estimates rows scanned, memory usage, and execution time for a ClickHouse
    SQL query, and suggests indexes based on WHERE-clause columns.

    \b
    The query can come from (in priority order):
      • --file query.sql      best for huge / multi-line queries
      • a QUERY argument       chqce "SELECT ..."
      • piped stdin            chqce < query.sql
      • interactive prompt     run with no query at all

    \b
    Environment variables (override defaults):
      CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_USER,
      CLICKHOUSE_PASSWORD, CLICKHOUSE_DATABASE

    \b
    Examples:
      chqce "SELECT count() FROM hits WHERE EventDate = today()"
      chqce -f report.sql --no-execute
      chqce -t 600 "SELECT ... a slow query ..."
      cat report.sql | chqce --max-query-size 1048576 --max-ast-elements 500000
    """
    try:
        resolved = _resolve_query(query, file)
    except OSError as e:
        _err.print(f"[red]Could not read query file:[/red] {e}")
        sys.exit(1)

    try:
        client = create_client(host=host, port=port, user=user,
                               password=password, database=database,
                               max_query_size=max_query_size,
                               max_execution_time=timeout,
                               max_ast_elements=max_ast_elements)
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

    if resolved:
        _run(resolved, estimator, client, database, execute)
    else:
        while True:
            q = _collect_interactive()
            if not q:
                continue
            _run(q, estimator, client, database, execute)
            console.print("[dim]" + "─" * 60 + "[/dim]")
