"""App factory da API principal."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dhf_avatars.router import router as avatars_router
from dhf_shared.config import get_settings
from dhf_shared.logging import configure_logging, get_logger
from dhf_storage.factory import get_storage_provider
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, jobs, storage, system_status


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, service="api")
    logger = get_logger(service="api")
    logger.info("api.startup", app_env=settings.app_env)
    yield
    await get_storage_provider().aclose()
    logger.info("api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Digital Human Video Factory API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(storage.router)
    app.include_router(system_status.router)
    app.include_router(jobs.router)
    app.include_router(avatars_router)
    return app


app = create_app()
