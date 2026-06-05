import pytest

from chqce.errors import classify_error


@pytest.mark.parametrize(
    "message, expected_category",
    [
        ("Code: 159. DB::Exception: Timeout exceeded: elapsed 30s (TIMEOUT_EXCEEDED)", "timeout"),
        ("HTTPDriver received ReadTimeout: Read timed out", "timeout"),
        ("max_execution_time has been exceeded", "timeout"),
        ("Code: 168. DB::Exception: AST is too big. Maximum: 50000 (TOO_BIG_AST)", "ast_too_big"),
        ("Setting max_ast_elements exceeded", "ast_too_big"),
        ("Code: 167. DB::Exception: Maximum parse depth (TOO_DEEP_RECURSION)", "parser_depth"),
        ("Code: 62. DB::Exception: Max query size exceeded", "query_size"),
        ("Code: 241. DB::Exception: Memory limit (for query) exceeded (MEMORY_LIMIT_EXCEEDED)", "memory"),
        ("Code: 158. DB::Exception: Limit for rows to read (TOO_MANY_ROWS)", "read_limit"),
        ("max_bytes_to_read exceeded", "read_limit"),
    ],
)
def test_classify_known_errors(message, expected_category):
    result = classify_error(message)
    assert result is not None
    assert result.category == expected_category
    assert result.title
    assert result.hint  # every known category ships an actionable hint


def test_classify_is_case_insensitive():
    assert classify_error("TIMEOUT EXCEEDED").category == "timeout"
    assert classify_error("timeout exceeded").category == "timeout"


def test_unknown_error_returns_none():
    assert classify_error("Code: 47. Unknown identifier 'foo'") is None


def test_empty_or_none_returns_none():
    assert classify_error(None) is None
    assert classify_error("") is None


def test_timeout_hint_mentions_flag():
    result = classify_error("Timeout exceeded")
    assert "--timeout" in result.hint
    assert "--no-execute" in result.hint


def test_ast_hint_mentions_flag():
    result = classify_error("AST is too big")
    assert "--max-ast-elements" in result.hint
