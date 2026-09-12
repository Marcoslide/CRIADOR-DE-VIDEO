"""Entrypoint Celery do job_worker: `celery -A worker.celery_app worker`.

Reexporta o app compartilhado de `dhf_shared` (mesma instância usada pela API para
enviar tasks) e importa os módulos de tasks para que sejam registrados no worker.
"""

from dhf_shared.celery_app import celery_app

from worker.tasks import health as _health  # noqa: F401 - registra as tasks

__all__ = ["celery_app"]
