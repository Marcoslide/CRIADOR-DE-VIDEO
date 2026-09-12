"""Módulos de tasks do job_worker. Cada domínio (Fase 3+) ganha seu próprio módulo aqui,
sempre importando `celery_app` de `dhf_shared.celery_app` e registrando com
`@celery_app.task(name="<dominio>.<acao>")`.
"""
