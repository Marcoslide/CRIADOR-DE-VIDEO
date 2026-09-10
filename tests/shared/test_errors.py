"""dhf_shared.errors.sanitize_error — nunca deixar host/porta/DSN/caminho vazar numa
resposta pública. Testa a classificação por TIPO, nunca por texto da exceção."""

import httpx
import redis.exceptions
import sqlalchemy.exc
from dhf_shared.errors import sanitize_error


def test_timeout_error_is_sanitized() -> None:
    result = sanitize_error(TimeoutError("timed out talking to db.internal.example:5432"))
    assert result.code == "timeout"
    assert "db.internal.example" not in result.message
    assert "5432" not in result.message


def test_httpx_timeout_is_sanitized() -> None:
    request = httpx.Request("GET", "https://internal-service.example/secret-path")
    result = sanitize_error(httpx.ConnectTimeout("connect timeout", request=request))
    assert result.code == "timeout"
    assert "internal-service.example" not in result.message


def test_connection_error_is_sanitized() -> None:
    result = sanitize_error(ConnectionError("Connection refused to 10.0.0.5:6379"))
    assert result.code == "connection_error"
    assert "10.0.0.5" not in result.message
    assert "6379" not in result.message


def test_httpx_transport_error_is_sanitized() -> None:
    request = httpx.Request("GET", "https://internal.example/x")
    result = sanitize_error(httpx.ConnectError("[Errno 111] Connection refused", request=request))
    assert result.code == "connection_error"
    assert "internal.example" not in result.message
    assert "Errno" not in result.message


def test_redis_connection_error_is_sanitized() -> None:
    result = sanitize_error(
        redis.exceptions.ConnectionError("Error 111 connecting to redis-prod.internal:6379.")
    )
    assert result.code == "connection_error"
    assert "redis-prod.internal" not in result.message


def test_sqlalchemy_operational_error_is_sanitized() -> None:
    exc = sqlalchemy.exc.OperationalError(
        "connect failed",
        params=None,
        orig=Exception(
            "connection to server at postgres.internal:5432 failed: "
            "FATAL: password authentication failed for user 'dhf'"
        ),
    )
    result = sanitize_error(exc)
    assert result.code == "connection_error"
    assert "postgres.internal" not in result.message
    assert "password" not in result.message


def test_httpx_status_error_401_is_auth_error() -> None:
    request = httpx.Request("GET", "https://www.googleapis.com/drive/v3/files")
    response = httpx.Response(401, request=request)
    result = sanitize_error(httpx.HTTPStatusError("401", request=request, response=response))
    assert result.code == "auth_error"


def test_httpx_status_error_429_is_rate_limited() -> None:
    request = httpx.Request("GET", "https://www.googleapis.com/drive/v3/files")
    response = httpx.Response(429, request=request)
    result = sanitize_error(httpx.HTTPStatusError("429", request=request, response=response))
    assert result.code == "rate_limited"


def test_httpx_status_error_500_is_upstream_error() -> None:
    request = httpx.Request("GET", "https://www.googleapis.com/drive/v3/files")
    response = httpx.Response(500, request=request)
    result = sanitize_error(httpx.HTTPStatusError("500", request=request, response=response))
    assert result.code == "upstream_error"
    assert "googleapis.com" not in result.message


def test_httpx_status_error_400_is_upstream_rejected() -> None:
    request = httpx.Request("GET", "https://www.googleapis.com/drive/v3/files")
    response = httpx.Response(400, request=request)
    result = sanitize_error(httpx.HTTPStatusError("400", request=request, response=response))
    assert result.code == "upstream_rejected"


def test_unknown_exception_falls_back_to_internal_error() -> None:
    result = sanitize_error(ValueError("/etc/secrets/service-account.json not found"))
    assert result.code == "internal_error"
    assert "/etc/secrets" not in result.message
    assert result.message == "Erro interno inesperado."
