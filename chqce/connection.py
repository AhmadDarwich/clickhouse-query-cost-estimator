import clickhouse_connect
from clickhouse_connect.driver import Client


def create_client(
    host: str = "localhost",
    port: int = 8123,
    user: str = "default",
    password: str = "",
    database: str = "default",
) -> Client:
    return clickhouse_connect.get_client(
        host=host,
        port=port,
        username=user,
        password=password,
        database=database,
        connect_timeout=10,
        send_receive_timeout=300,
    )


def test_connection(client: Client) -> tuple[bool, str]:
    try:
        result = client.query("SELECT version()")
        version = result.result_rows[0][0]
        return True, version
    except Exception as e:
        return False, str(e)
