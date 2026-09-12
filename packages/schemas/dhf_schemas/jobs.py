"""Contratos do job de diagnóstico (prova real API -> Redis -> Worker). Ver
`docs/ARCHITECTURE.md` §16 (Render Queue) para o desenho completo de filas de produção —
isto é só o encanamento mínimo para provar que o caminho funciona.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class JobState(StrEnum):
    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class DiagnosticJobSubmitted(BaseModel):
    job_id: str
    triggered_at: datetime


class DiagnosticJobStatus(BaseModel):
    job_id: str
    state: JobState
    result: dict | None = None
