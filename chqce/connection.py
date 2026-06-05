import clickhouse_connect
from clickhouse_connect.driver import Client


DEFAULT_SOCKET_TIMEOUT = 300


def create_client(
    host: str = "localhost",
    port: int = 8123,
    user: str = "default",
    password: str = "",
    database: str = "default",
    max_query_size: int = 0,
    max_execution_time: int = 0,
    max_ast_elements: int = 0,
) -> Client:
    # Per-session ClickHouse settings, only sent when the caller overrides them.
    settings = {}
    if max_query_size > 0:
        # ClickHouse rejects queries larger than max_query_size (256 KiB default).
        settings["max_query_size"] = max_query_size
    if max_execution_time > 0:
        # Server aborts the query after this many seconds (0 = unlimited).
        settings["max_execution_time"] = max_execution_time
    if max_ast_elements > 0:
        # Raises the limit on parsed-query size (huge IN-lists, deep nesting).
        settings["max_ast_elements"] = max_ast_elements
        settings["max_expanded_ast_elements"] = max_ast_elements

    # Keep the client socket alive a bit longer than the server-side limit so
    # ClickHouse returns a clean timeout error instead of the socket dropping.
    socket_timeout = DEFAULT_SOCKET_TIMEOUT
    if max_execution_time > 0:
        socket_timeout = max_execution_time + 30

    return clickhouse_connect.get_client(
        host=host,
        port=port,
        username=user,
        password=password,
        database=database,
        connect_timeout=10,
        send_receive_timeout=socket_timeout,
        settings=settings,
    )


def test_connection(client: Client) -> tuple[bool, str]:
    try:
        result = client.query("SELECT version()")
        version = result.result_rows[0][0]
        return True, version
    except Exception as e:
        return False, str(e)
