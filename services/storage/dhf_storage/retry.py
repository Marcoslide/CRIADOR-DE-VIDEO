"""Retry com backoff exponencial + jitter para chamadas transitoriamente instáveis à
Drive API. Só repete 429 (quota) e 5xx / erro de transporte — qualquer outro erro (404,
401, 403 fora de rate limit, etc.) propaga na primeira tentativa, nunca retry cego.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

T = TypeVar("T")


class RetryExhaustedError(Exception):
    def __init__(self, attempts: int, last_error: BaseException) -> None:
        super().__init__(f"esgotadas {attempts} tentativas — último erro: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


async def with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> T:
    last_error: BaseException | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in RETRYABLE_STATUS:
                raise
            last_error = exc
        except httpx.TransportError as exc:
            last_error = exc

        if attempt == max_retries:
            break

        delay = base_delay_s * (2**attempt) + random.uniform(0, base_delay_s)
        if logger is not None:
            logger.warning(
                "storage.retry",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay_s=round(delay, 2),
                error=str(last_error),
            )
        await asyncio.sleep(delay)

    assert last_error is not None  # loop só chega aqui depois de capturar >=1 erro
    raise RetryExhaustedError(max_retries + 1, last_error)
