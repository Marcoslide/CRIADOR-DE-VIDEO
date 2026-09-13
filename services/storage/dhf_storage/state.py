"""Persistência local mínima do ID da root gerenciada pelo aplicativo."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


class RootStateError(RuntimeError):
    """O state file existe, mas não contém um estado válido."""


@dataclass(frozen=True)
class RootState:
    root_folder_id: str
    root_folder_name: str
    version: int = 1


def load_root_state(path: Path | None) -> RootState | None:
    if path is None or not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RootStateError("não foi possível carregar o state file da root") from exc
    if not isinstance(raw, dict):
        raise RootStateError("state file da root precisa conter um objeto JSON")
    if raw.get("version") != 1:
        raise RootStateError("versão desconhecida no state file da root")
    folder_id = raw.get("root_folder_id")
    folder_name = raw.get("root_folder_name")
    if not isinstance(folder_id, str) or not folder_id.strip():
        raise RootStateError("root_folder_id ausente no state file")
    if not isinstance(folder_name, str) or not folder_name.strip():
        raise RootStateError("root_folder_name ausente no state file")
    return RootState(root_folder_id=folder_id, root_folder_name=folder_name)


def save_root_state(path: Path, state: RootState) -> None:
    parent_already_existed = path.parent.exists()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not parent_already_existed:
        os.chmod(path.parent, 0o700)

    payload = {
        "version": state.version,
        "root_folder_id": state.root_folder_id,
        "root_folder_name": state.root_folder_name,
    }
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            Path(temporary_name).unlink(missing_ok=True)
        except OSError:
            pass
