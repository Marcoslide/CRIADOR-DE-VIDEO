"""Status real do Storage (Google Drive) — nunca simula conexão.

GET /storage/status faz uma checagem real (cacheada por GOOGLE_DRIVE_STATUS_CACHE_TTL_S
segundos) contra a Drive API. `?force_refresh=true` ignora o cache.
"""

from dhf_schemas.storage import StorageStatus
from dhf_storage.factory import get_storage_provider
from fastapi import APIRouter, Query

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/status", response_model=StorageStatus)
async def storage_status(force_refresh: bool = Query(default=False)) -> StorageStatus:
    provider = get_storage_provider()
    return await provider.get_status(force_refresh=force_refresh)
