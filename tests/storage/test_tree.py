"""Testes puros da árvore oficial — sem rede, sem mocks."""

from dhf_storage.tree import (
    INTEGRATION_TESTS_PREFIX,
    OFFICIAL_TOP_LEVEL_FOLDERS,
    is_within_scratch,
    validate_tree,
)


def test_official_tree_has_18_folders() -> None:
    assert len(OFFICIAL_TOP_LEVEL_FOLDERS) == 18
    assert len(set(OFFICIAL_TOP_LEVEL_FOLDERS)) == 18  # sem duplicatas


def test_validate_tree_complete_and_exact() -> None:
    result = validate_tree(OFFICIAL_TOP_LEVEL_FOLDERS)
    assert result.valid is True
    assert result.missing == []
    assert result.unexpected == []
    assert set(result.found) == set(OFFICIAL_TOP_LEVEL_FOLDERS)


def test_validate_tree_reports_missing() -> None:
    found = OFFICIAL_TOP_LEVEL_FOLDERS[:-2]  # faltam as 2 últimas
    result = validate_tree(found)
    assert result.valid is False
    assert set(result.missing) == set(OFFICIAL_TOP_LEVEL_FOLDERS[-2:])


def test_validate_tree_extra_folder_is_not_a_failure() -> None:
    found = [*OFFICIAL_TOP_LEVEL_FOLDERS, "ALGO_EXTRA_QUE_NAO_ESPERAVAMOS"]
    result = validate_tree(found)
    assert result.valid is True  # nada oficial falta
    assert result.unexpected == ["ALGO_EXTRA_QUE_NAO_ESPERAVAMOS"]


def test_validate_tree_ignores_known_internal_integration_folder() -> None:
    found = [*OFFICIAL_TOP_LEVEL_FOLDERS, INTEGRATION_TESTS_PREFIX]
    result = validate_tree(found)
    assert result.valid is True
    assert result.unexpected == []


def test_validate_tree_empty() -> None:
    result = validate_tree([])
    assert result.valid is False
    assert len(result.missing) == 18


def test_is_within_scratch() -> None:
    assert is_within_scratch("02_SISTEMA_STORAGE/_tmp/teste.bin") is True
    assert is_within_scratch("02_SISTEMA_STORAGE/_tmp") is True
    assert is_within_scratch("/02_SISTEMA_STORAGE/_tmp/teste.bin/") is True
    assert is_within_scratch("02_SISTEMA_STORAGE/outra_coisa/teste.bin") is False
    assert is_within_scratch("_integration_tests/abc123/teste.bin") is True
    assert is_within_scratch("_integration_tests") is True
    assert is_within_scratch("_integration_tests_falso/abc123/teste.bin") is False
    assert is_within_scratch("03_AVATAR_IDENTITY_FOTOS/lia/v1/head360/000.png") is False
