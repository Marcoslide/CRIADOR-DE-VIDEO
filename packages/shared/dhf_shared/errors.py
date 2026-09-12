"""Sanitização de erros para respostas públicas de API.

Regra: nenhum endpoint público devolve `str(exc)`, URL interna, hostname/porta ou stack
trace — a mensagem de uma ConnectionError/OperationalError tipicamente contém DSN,
host:porta ou caminho de arquivo. O erro completo continua indo para o log estruturado
(`dhf_shared.logging`); quem chama `sanitize_error()` deve logar a exceção original antes
de expor só o resultado sanitizado ao cliente.
"""

from dataclasses import dataclass

import celery.exceptions
import httpx
import redis.exceptions
import sqlalchemy.exc


@dataclass(frozen=True)
class SanitizedError:
    code: str
    message: str


def sanitize_error(exc: BaseException) -> SanitizedError:
    """Classifica pelo TIPO da exceção, nunca pelo texto dela."""
    # celery.exceptions.TimeoutError NÃO herda do TimeoutError embutido do Python — é uma
    # classe própria (CeleryError -> TaskError -> TimeoutError), levantada por
    # `AsyncResult.get(timeout=...)` quando o worker não responde a tempo.
    if isinstance(
        exc,
        TimeoutError
        | httpx.TimeoutException
        | redis.exceptions.TimeoutError
        | celery.exceptions.TimeoutError,
    ):
        return SanitizedError("timeout", "A operação excedeu o tempo limite.")

    if isinstance(
        exc,
        ConnectionError
        | httpx.TransportError
        | redis.exceptions.ConnectionError
        | sqlalchemy.exc.OperationalError,
    ):
        return SanitizedError("connection_error", "Não foi possível conectar ao serviço.")

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return SanitizedError("auth_error", "Falha de autenticação com o serviço externo.")
        if status == 429:
            return SanitizedError(
                "rate_limited", "Limite de requisições do serviço externo atingido."
            )
        if status >= 500:
            return SanitizedError("upstream_error", "O serviço externo respondeu com erro.")
        return SanitizedError("upstream_rejected", "O serviço externo rejeitou a requisição.")

    return SanitizedError("internal_error", "Erro interno inesperado.")
