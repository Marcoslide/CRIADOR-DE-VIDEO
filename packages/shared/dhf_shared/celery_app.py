"""App Celery compartilhado por `apps/api` (cliente) e `workers/job_worker` (worker).

Ambos os processos importam o mesmo `celery_app` — é isso que garante que o nome
da task ("health.ping") bata entre quem envia e quem executa, mesmo em processos
separados. Tasks de domínio (Fase 3+) devem seguir o mesmo padrão: importar
`celery_app` daqui e registrar com `@celery_app.task(name="<dominio>.<acao>")`.
"""

from datetime import UTC, datetime

from celery import Celery

from dhf_shared.config import get_settings


def _build_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "dhf",
        broker=settings.resolved_celery_broker_url,
        backend=settings.resolved_celery_result_backend,
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
    )
    return app


celery_app = _build_celery_app()


@celery_app.task(name="health.ping")
def ping() -> dict:
    return {"pong": True, "ts": datetime.now(UTC).isoformat()}
