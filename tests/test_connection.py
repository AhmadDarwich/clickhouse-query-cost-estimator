import chqce.connection as connection
from conftest import FakeClient, make_handler


class _Capture:
    """Captures kwargs passed to clickhouse_connect.get_client."""

    def __init__(self):
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return object()  # the returned client is irrelevant here


def _patch_get_client(monkeypatch):
    cap = _Capture()
    monkeypatch.setattr(connection.clickhouse_connect, "get_client", cap)
    return cap


def test_create_client_passes_basic_params(monkeypatch):
    cap = _patch_get_client(monkeypatch)
    connection.create_client(host="h", port=9000, user="u", password="p", database="db")
    assert cap.kwargs["host"] == "h"
    assert cap.kwargs["port"] == 9000
    assert cap.kwargs["username"] == "u"
    assert cap.kwargs["password"] == "p"
    assert cap.kwargs["database"] == "db"


def test_create_client_no_optional_settings_by_default(monkeypatch):
    cap = _patch_get_client(monkeypatch)
    connection.create_client()
    assert cap.kwargs["settings"] == {}
    assert cap.kwargs["send_receive_timeout"] == connection.DEFAULT_SOCKET_TIMEOUT


def test_create_client_sets_max_query_size(monkeypatch):
    cap = _patch_get_client(monkeypatch)
    connection.create_client(max_query_size=1048576)
    assert cap.kwargs["settings"]["max_query_size"] == 1048576


def test_create_client_sets_ast_elements_both_keys(monkeypatch):
    cap = _patch_get_client(monkeypatch)
    connection.create_client(max_ast_elements=500000)
    settings = cap.kwargs["settings"]
    assert settings["max_ast_elements"] == 500000
    assert settings["max_expanded_ast_elements"] == 500000


def test_create_client_timeout_bumps_socket(monkeypatch):
    cap = _patch_get_client(monkeypatch)
    connection.create_client(max_execution_time=120)
    assert cap.kwargs["settings"]["max_execution_time"] == 120
    # Socket timeout must outlast the server-side limit.
    assert cap.kwargs["send_receive_timeout"] == 150


def test_test_connection_success():
    client = FakeClient(make_handler(version="24.1.0.0"))
    ok, value = connection.test_connection(client)
    assert ok is True
    assert value == "24.1.0.0"


def test_test_connection_failure():
    def boom(sql, parameters=None):
        raise RuntimeError("refused")

    client = FakeClient(boom)
    ok, value = connection.test_connection(client)
    assert ok is False
    assert "refused" in value
