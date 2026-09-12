"""Logging estruturado (JSON) compartilhado por api e workers.

Campos padrão: timestamp, level, event. Campos contextuais (project_id, scene_id,
avatar_id, job_id, provider, gpu, stage, duration, status, error, vram, cost) são
anexados via `.bind(...)` a partir das entidades que os introduzem (Fase 3+).
"""

import logging
import sys

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", service: str = "dhf") -> None:
    global _CONFIGURED

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True
    get_logger(service=service).info("logging.configured", level=level.upper())


def get_logger(**initial_context: object) -> structlog.stdlib.BoundLogger:
    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger().bind(**initial_context)
