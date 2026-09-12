"""Primitivas REST de baixo nível contra a Google Drive API v3.

Funções puras (recebem `httpx.AsyncClient` + token de acesso, não guardam estado). Cada
chamada de rede passa por `with_retry`. `google_drive.py` compõe estas primitivas para
implementar `StorageProvider`.
"""

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from dhf_storage.retry import with_retry

FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
METADATA_FIELDS = "id,name,size,mimeType,md5Checksum,modifiedTime,webViewLink,parents"

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _escape_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def list_children(
    client: httpx.AsyncClient,
    token: str,
    parent_id: str,
    *,
    name: str | None = None,
    folders_only: bool = False,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> list[dict[str, Any]]:
    """Lista (com paginação completa) os filhos não-lixeira de `parent_id`, opcionalmente
    filtrando por nome exato e/ou só pastas."""
    query = f"'{parent_id}' in parents and trashed = false"
    if name is not None:
        query += f" and name = '{_escape_query_value(name)}'"
    if folders_only:
        query += f" and mimeType = '{FOLDER_MIME_TYPE}'"

    results: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params = {
            "q": query,
            "fields": f"nextPageToken,files({METADATA_FIELDS})",
            "pageSize": 200,
            "spaces": "drive",
        }
        if page_token:
            params["pageToken"] = page_token

        async def _call(p=params):
            response = await client.get(FILES_URL, params=p, headers=_auth_headers(token))
            response.raise_for_status()
            return response.json()

        payload = await with_retry(
            _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
        )
        results.extend(payload.get("files", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return results


async def create_folder(
    client: httpx.AsyncClient,
    token: str,
    parent_id: str,
    name: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, Any]:
    async def _call():
        response = await client.post(
            FILES_URL,
            params={"fields": METADATA_FIELDS},
            headers={**_auth_headers(token), "Content-Type": "application/json"},
            json={"name": name, "mimeType": FOLDER_MIME_TYPE, "parents": [parent_id]},
        )
        response.raise_for_status()
        return response.json()

    return await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )


async def initiate_resumable_upload(
    client: httpx.AsyncClient,
    token: str,
    parent_id: str,
    name: str,
    mime_type: str,
    size_bytes: int,
    *,
    existing_file_id: str | None = None,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> str:
    """Retorna a Location (URL da sessão de upload). Se `existing_file_id` for informado,
    atualiza o conteúdo desse arquivo (PATCH) em vez de criar um novo (POST) — é assim que
    upload() evita duplicar arquivos quando o remote_path já existe."""
    if existing_file_id:
        method, url = "PATCH", f"{UPLOAD_URL}/{existing_file_id}"
    else:
        method, url = "POST", UPLOAD_URL

    async def _call():
        response = await client.request(
            method,
            url,
            params={"uploadType": "resumable", "fields": METADATA_FIELDS},
            headers={
                **_auth_headers(token),
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(size_bytes),
            },
            json={"name": name} if existing_file_id else {"name": name, "parents": [parent_id]},
        )
        response.raise_for_status()
        return response

    response = await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )
    location = response.headers.get("Location")
    if not location:
        raise RuntimeError("Drive não retornou Location para a sessão de upload resumable")
    return location


async def upload_content_stream(
    client: httpx.AsyncClient,
    upload_url: str,
    content_factory: Callable[[], AsyncIterator[bytes]],
    mime_type: str,
    size_bytes: int,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, Any]:
    """Envia o corpo inteiro em streaming num único PUT. Não implementa retomada parcial
    após falha a meio do upload — nesse caso, o próprio with_retry refaz a tentativa
    inteira (ver docs/STORAGE_GOOGLE_DRIVE.md).

    `content_factory` — e não um AsyncIterator já pronto — de propósito: um stream
    assíncrono não pode ser relido do início depois de (parcialmente) consumido. Se
    passássemos o mesmo iterator para cada tentativa do with_retry, um retry depois de
    uma falha a meio do envio mandaria um corpo vazio/truncado sem erro nenhum — corrupção
    silenciosa. `content_factory()` é chamada de novo a cada tentativa, reabrindo o arquivo
    do byte 0 (ver GoogleDriveStorageProvider._read_chunks)."""

    async def _call():
        response = await client.put(
            upload_url,
            content=content_factory(),
            headers={"Content-Type": mime_type, "Content-Length": str(size_bytes)},
        )
        response.raise_for_status()
        return response.json()

    return await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )


async def get_file_metadata(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, Any]:
    async def _call():
        response = await client.get(
            f"{FILES_URL}/{file_id}",
            params={"fields": METADATA_FIELDS},
            headers=_auth_headers(token),
        )
        response.raise_for_status()
        return response.json()

    return await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )


async def download_stream(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
) -> AsyncIterator[bytes]:
    """Não usa with_retry (o corpo é um generator consumido pelo caller — retry teria que
    envolver o caller inteiro). Erros de status são levantados ao abrir a resposta."""
    async with client.stream(
        "GET",
        f"{FILES_URL}/{file_id}",
        params={"alt": "media"},
        headers=_auth_headers(token),
    ) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            yield chunk


async def trash_file(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> None:
    async def _call():
        response = await client.patch(
            f"{FILES_URL}/{file_id}",
            headers={**_auth_headers(token), "Content-Type": "application/json"},
            json={"trashed": True},
        )
        response.raise_for_status()
        return None

    await with_retry(_call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger)


async def delete_file_permanently(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> None:
    async def _call():
        response = await client.delete(f"{FILES_URL}/{file_id}", headers=_auth_headers(token))
        if response.status_code != 404:
            response.raise_for_status()
        return None

    await with_retry(_call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger)


async def copy_file(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
    new_name: str,
    new_parent_id: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, Any]:
    async def _call():
        response = await client.post(
            f"{FILES_URL}/{file_id}/copy",
            params={"fields": METADATA_FIELDS},
            headers={**_auth_headers(token), "Content-Type": "application/json"},
            json={"name": new_name, "parents": [new_parent_id]},
        )
        response.raise_for_status()
        return response.json()

    return await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )


async def move_file(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
    new_name: str,
    old_parent_id: str,
    new_parent_id: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, Any]:
    async def _call():
        response = await client.patch(
            f"{FILES_URL}/{file_id}",
            params={
                "addParents": new_parent_id,
                "removeParents": old_parent_id,
                "fields": METADATA_FIELDS,
            },
            headers={**_auth_headers(token), "Content-Type": "application/json"},
            json={"name": new_name},
        )
        response.raise_for_status()
        return response.json()

    return await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )
