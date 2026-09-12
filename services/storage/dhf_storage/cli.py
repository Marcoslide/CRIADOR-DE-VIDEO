"""CLI do Storage — verifica conexão real e a árvore oficial de pastas.

    uv run --project services/storage dhf-storage check
    uv run --project services/storage python -m dhf_storage check

Nunca imprime token ou conteúdo de credencial — só o status e a árvore.
"""

import argparse
import asyncio
import sys

from dhf_storage.factory import get_storage_provider


async def _check() -> int:
    provider = get_storage_provider()
    try:
        status = await provider.get_status(force_refresh=True)
    finally:
        await provider.aclose()

    print(f"status: {status.status.value}")
    if status.detail:
        print(f"detail: {status.detail}")
    if status.root_folder_id:
        print(f"root_folder_id: {status.root_folder_id}")
    if status.tree:
        print(
            f"árvore oficial: {len(status.tree.found)}/{len(status.tree.expected)} "
            "pastas encontradas"
        )
        if status.tree.missing:
            print("faltando:")
            for name in status.tree.missing:
                print(f"  - {name}")
        if status.tree.unexpected:
            print("pastas extras na raiz (fora da lista oficial, não é erro):")
            for name in status.tree.unexpected:
                print(f"  - {name}")

    return 0 if status.status.value == "connected" else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dhf-storage", description="CLI do Storage (Google Drive)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="verifica conexão e a árvore oficial de pastas")

    args = parser.parse_args()

    if args.command == "check":
        sys.exit(asyncio.run(_check()))


if __name__ == "__main__":
    main()
