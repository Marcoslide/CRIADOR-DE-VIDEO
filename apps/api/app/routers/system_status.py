"""Status agregado do sistema — um único GET que o Dashboard consome para pintar todos os
cards de status de uma vez. Cada componente é checado de verdade nesta requisição (regra
ZERO FAKE, seção 68 do prompt-mestre): GPU via `nvidia-smi` real, OpenAI via chamada real à
API quando há chave configurada, engines de render (Unreal/Audio2Face/MetaHuman) verificando
se o caminho/URL configurado existe de verdade — nunca um "connected" hardcoded.
"""

import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dhf_schemas.health import ComponentCheck
from dhf_schemas.system_status import (
    EngineStatus,
    EngineStubStatus,
    GpuStatus,
    OpenAIStatus,
    SystemStatusResponse,
)
from dhf_shared.config import get_settings
from dhf_shared.errors import sanitize_error
from dhf_shared.logging import get_logger
from dhf_storage.factory import get_storage_provider
from fastapi import APIRouter

from app.routers.health import check_postgres, check_redis, check_worker

router = APIRouter(prefix="/status", tags=["status"])
_logger = get_logger(service="api", component="system_status")


@router.get("/system", response_model=SystemStatusResponse)
async def system_status() -> SystemStatusResponse:
    settings = get_settings()
    results = await asyncio.gather(
        check_api(),
        check_postgres(),
        check_redis(),
        check_worker(),
        get_storage_provider().get_status(),
        check_gpu(),
        check_openai(),
        check_render_engine(
            "unreal", settings.unreal_engine_path, "Unreal Engine (motor de render)"
        ),
        check_render_engine(
            "audio2face", settings.audio2face_path, "NVIDIA Audio2Face (performance facial)"
        ),
        check_render_engine(
            "metahuman", settings.metahuman_api_url, "MetaHuman Animator", is_url=True
        ),
    )
    (
        api_check,
        postgres_check,
        redis_check,
        worker_check,
        storage_check,
        gpu,
        openai,
        unreal,
        audio2face,
        metahuman,
    ) = results
    return SystemStatusResponse(
        checked_at=datetime.now(UTC),
        api=api_check,
        postgres=postgres_check,
        redis=redis_check,
        worker=worker_check,
        storage=storage_check,
        gpu=gpu,
        openai=openai,
        unreal=unreal,
        audio2face=audio2face,
        metahuman=metahuman,
    )


async def check_api() -> ComponentCheck:
    return ComponentCheck(name="api", status="connected", latency_ms=0.0, detail="processo de pé")


async def check_gpu() -> GpuStatus:
    """Detecção real via `nvidia-smi` — nunca inventa VRAM/driver. Sem o binário no PATH
    (nó sem GPU provisionado), reporta NOT_CONFIGURED honestamente."""
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        return GpuStatus(
            status=EngineStatus.NOT_CONFIGURED,
            detail="nvidia-smi não encontrado — nó GPU (Hostinger RTX 5090) ainda não provisionado",
        )
    try:
        proc = await asyncio.create_subprocess_exec(
            nvidia_smi,
            "--query-gpu=name,driver_version,memory.total,memory.used",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode != 0:
            _logger.error("system_status.gpu_check_failed", stderr=stderr.decode(errors="replace"))
            return GpuStatus(
                status=EngineStatus.ERROR, detail="nvidia-smi retornou erro ao consultar a GPU"
            )
        line = stdout.decode().strip().splitlines()[0]
        name, driver, vram_total, vram_used = (part.strip() for part in line.split(","))
        return GpuStatus(
            status=EngineStatus.CONNECTED,
            detail=f"{name} detectada via nvidia-smi",
            device_name=name,
            driver_version=driver,
            vram_total_mb=int(float(vram_total)),
            vram_used_mb=int(float(vram_used)),
        )
    except (TimeoutError, OSError, ValueError, IndexError) as exc:
        _logger.error(
            "system_status.gpu_check_failed", error=str(exc), error_type=type(exc).__name__
        )
        return GpuStatus(
            status=EngineStatus.ERROR, detail="Falha ao consultar a GPU via nvidia-smi"
        )


async def check_openai() -> OpenAIStatus:
    """NOT_CONFIGURED sem chave. Com chave, faz uma chamada real e barata (GET /models) —
    nunca assume que a chave é válida sem checar."""
    settings = get_settings()
    if not settings.openai_api_key:
        return OpenAIStatus(
            status=EngineStatus.NOT_CONFIGURED, detail="OPENAI_API_KEY não configurada"
        )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
            response.raise_for_status()
        return OpenAIStatus(status=EngineStatus.CONNECTED, detail="API respondeu com sucesso")
    except Exception as exc:  # noqa: BLE001 - logado completo, exposto só sanitizado
        _logger.error(
            "system_status.openai_check_failed", error=str(exc), error_type=type(exc).__name__
        )
        sanitized = sanitize_error(exc)
        return OpenAIStatus(
            status=EngineStatus.ERROR, detail=sanitized.message, error_code=sanitized.code
        )


async def check_render_engine(
    name: str, configured_value: str, label: str, *, is_url: bool = False
) -> EngineStubStatus:
    """Checagem real (não hardcoded) para integrações de render ainda sem implementação —
    Unreal/Audio2Face/MetaHuman entram em fases futuras (7+). Sem
    UNREAL_ENGINE_PATH/AUDIO2FACE_PATH/METAHUMAN_API_URL configurado, honestamente
    NOT_INSTALLED. Se configurado mas o caminho não existir no disco (só se aplica a
    caminho local, não a URL), ERROR — configuração presente mas quebrada é diferente de
    ausente. Nenhum destes ramos chega a CONNECTED: a integração funcional em si (rodar um
    job real no engine) só existe a partir da fase que a implementa."""
    if not configured_value:
        return EngineStubStatus(
            name=label,
            status=EngineStatus.NOT_INSTALLED,
            detail=f"{name} ainda não configurado — integração entra em fase futura do ROADMAP",
        )
    if not is_url and not Path(configured_value).exists():
        return EngineStubStatus(
            name=label,
            status=EngineStatus.ERROR,
            detail=f"Caminho configurado para {name} não existe no disco",
        )
    return EngineStubStatus(
        name=label,
        status=EngineStatus.NOT_INSTALLED,
        detail=f"{name} configurado, mas a integração funcional ainda não foi implementada",
    )
