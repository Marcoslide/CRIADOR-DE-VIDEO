"""Task de health check — validação real do round-trip API -> Redis -> worker."""

from dhf_shared.celery_app import ping  # noqa: F401 - task já registrada em dhf_shared
