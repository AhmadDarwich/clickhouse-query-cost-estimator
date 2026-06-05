import clickhouse_connect
from clickhouse_connect.driver import Client


def create_client(
    host: str = "localhost",
    port: int = 8123,
    user: str = "default",
    password: str = "",
    database: str = "default",
    max_query_size: int = 0,
) -> Client:
    # ClickHouse rejects queries larger than max_query_size (default 256 KiB).
    # Raise it per-session for very large queries when the caller asks.
    settings = {}
    if max_query_size > 0:
        settings["max_query_size"] = max_query_size

    return clickhouse_connect.get_client(
        host=host,
        port=port,
        username=user,
        password=password,
        database=database,
        connect_timeout=10,
        send_receive_timeout=300,
        settings=settings,
    )


def test_connection(client: Client) -> tuple[bool, str]:
    try:
        result = client.query("SELECT version()")
        version = result.result_rows[0][0]
        return True, version
    except Exception as e:
        return False, str(e)
