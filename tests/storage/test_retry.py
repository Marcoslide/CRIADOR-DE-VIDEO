"""with_retry — sem rede real: os "erros" são levantados por uma função fake."""

import httpx
import pytest
from dhf_storage.retry import RetryExhaustedError, with_retry


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.invalid/x")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


async def test_succeeds_without_retry() -> None:
    calls = 0

    async def func():
        nonlocal calls
        calls += 1
        return "ok"

    result = await with_retry(func, max_retries=3, base_delay_s=0)
    assert result == "ok"
    assert calls == 1


async def test_retries_on_500_then_succeeds() -> None:
    calls = 0

    async def func():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _http_error(500)
        return "ok"

    result = await with_retry(func, max_retries=5, base_delay_s=0)
    assert result == "ok"
    assert calls == 3


async def test_retries_on_429() -> None:
    calls = 0

    async def func():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise _http_error(429)
        return "ok"

    result = await with_retry(func, max_retries=5, base_delay_s=0)
    assert result == "ok"
    assert calls == 2


async def test_does_not_retry_on_404() -> None:
    calls = 0

    async def func():
        nonlocal calls
        calls += 1
        raise _http_error(404)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await with_retry(func, max_retries=5, base_delay_s=0)
    assert exc_info.value.response.status_code == 404
    assert calls == 1  # nenhuma tentativa extra


async def test_exhausts_retries_and_raises_retry_exhausted_error() -> None:
    calls = 0

    async def func():
        nonlocal calls
        calls += 1
        raise _http_error(500)

    with pytest.raises(RetryExhaustedError) as exc_info:
        await with_retry(func, max_retries=2, base_delay_s=0)
    assert calls == 3  # tentativa inicial + 2 retries
    assert exc_info.value.attempts == 3


async def test_retries_on_transport_error() -> None:
    calls = 0

    async def func():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise httpx.ConnectError("conexão recusada", request=httpx.Request("GET", "https://x"))
        return "ok"

    result = await with_retry(func, max_retries=3, base_delay_s=0)
    assert result == "ok"
    assert calls == 2
