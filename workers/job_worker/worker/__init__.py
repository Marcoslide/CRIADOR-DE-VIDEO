"""dhf-job-worker — worker Celery de jobs gerais (não-GPU): preparar avatar, processar
voz, criar Scene Plan, executar QA, exportar — a partir da Fase 3.

Na Fase 1 este worker existe apenas como processo real de infraestrutura, registrando
a task `health.ping` definida em `dhf_shared.celery_app` para validar o round-trip
completo via Redis.
"""
