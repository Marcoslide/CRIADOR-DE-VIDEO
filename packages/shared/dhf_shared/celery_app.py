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
        result_expires=settings.diagnostic_job_ttl_s,
        broker_connection_retry_on_startup=True,
        broker_transport_options={
            "socket_connect_timeout": 2,
            "socket_timeout": 5,
            "retry_policy": {"max_retries": 2, "interval_start": 0, "interval_step": 0.5},
        },
        result_backend_transport_options={
            "socket_connect_timeout": 2,
            "socket_timeout": 5,
            "retry_policy": {"max_retries": 2, "interval_start": 0, "interval_step": 0.5},
        },
    )
    return app


celery_app = _build_celery_app()


@celery_app.task(name="health.ping")
def ping() -> dict:
    return {"pong": True, "ts": datetime.now(UTC).isoformat()}


@celery_app.task(name="system.diagnostic_job")
def diagnostic_job(triggered_at: str) -> dict:
    """Job mínimo de diagnóstico: prova de ponta a ponta API -> Redis -> Worker.

    `triggered_at` é o timestamp de quando a API enfileirou o job (não de agora) — quem
    consome o resultado consegue comparar os dois timestamps e ver o round-trip real.
    """
    return {
        "status": "OK",
        "triggered_at": triggered_at,
        "processed_at": datetime.now(UTC).isoformat(),
    }
