"""Persistência atômica do ID da root gerenciada."""

import stat

import pytest
from dhf_storage.state import RootState, RootStateError, load_root_state, save_root_state


def test_root_state_roundtrip_uses_private_file(tmp_path) -> None:
    path = tmp_path / "private" / "drive-state.json"
    state = RootState(
        root_folder_id="managed-root-id",
        root_folder_name="CRIADOR DE VIDEO — STORAGE",
    )

    save_root_state(path, state)

    assert load_root_state(path) == state
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_missing_root_state_returns_none(tmp_path) -> None:
    assert load_root_state(tmp_path / "missing.json") is None


def test_corrupt_root_state_is_rejected(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text("not json")
    with pytest.raises(RootStateError, match="carregar"):
        load_root_state(path)
