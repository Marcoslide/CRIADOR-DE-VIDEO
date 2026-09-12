"""Ponto único de composição: quem precisa de armazenamento chama get_storage_provider().

`@lru_cache` dá uma instância por processo (reaproveita cliente HTTP, cache de pastas e
credencial carregada) — o mesmo padrão já usado em dhf_shared.config.get_settings().
"""

from functools import lru_cache

from dhf_storage.google_drive import GoogleDriveStorageProvider


@lru_cache
def get_storage_provider() -> GoogleDriveStorageProvider:
    return GoogleDriveStorageProvider()
