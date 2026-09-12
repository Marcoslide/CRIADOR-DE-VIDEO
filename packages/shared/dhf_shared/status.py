"""Taxonomia de status para qualquer integração externa (Provider Pattern).

Regra ZERO FAKE: nenhuma UI ou API pode reportar um provider como funcionando
("connected") quando na verdade ele está ausente, não configurado ou mockado.
Todo Provider real expõe um destes status — nunca um booleano solto.
"""

from enum import StrEnum


class ProviderStatus(StrEnum):
    REAL = "real"
    DEVELOPMENT = "development"
    MOCK = "mock"
    NOT_CONFIGURED = "not_configured"
    NOT_INSTALLED = "not_installed"
    ERROR = "error"
