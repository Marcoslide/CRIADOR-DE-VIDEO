"""Cache controlado (em memória, por instância do provider) de IDs de pasta já
descobertos/criados — evita repetir list/search na Drive API para o mesmo caminho lógico.

Controlado = interface explícita de leitura/escrita/invalidação, não um cache implícito
escondido dentro de chamadas HTTP. Sem TTL: uma vez que uma pasta existe no Drive com um
dado ID, essa associação (caminho lógico → ID) não expira sozinha; só é invalidada se o
próprio provider apagar/mover a entrada.
"""


class FolderIdCache:
    def __init__(self) -> None:
        self._by_path: dict[str, str] = {}

    def get(self, path: str) -> str | None:
        return self._by_path.get(path)

    def set(self, path: str, folder_id: str) -> None:
        self._by_path[path] = folder_id

    def invalidate(self, path: str | None = None) -> None:
        if path is None:
            self._by_path.clear()
        else:
            self._by_path.pop(path, None)

    def snapshot(self) -> dict[str, str]:
        return dict(self._by_path)
