"""CLI do Storage — verifica conexão real e a árvore oficial de pastas.

    uv run --project services/storage dhf-storage check
    uv run --project services/storage python -m dhf_storage check

Nunca imprime token ou conteúdo de credencial — só o status e a árvore.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from dhf_storage.auth import CredentialLoadError, authorize_oauth_user
from dhf_storage.config import GoogleDriveAuthMode, get_google_drive_settings
from dhf_storage.factory import get_storage_provider
from dhf_storage.google_drive import GoogleDriveStorageProvider


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
    if status.auth_mode:
        print(f"auth_mode: {status.auth_mode.value}")
    if status.drive_kind:
        print(f"drive_kind: {status.drive_kind.value}")
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


def _authorize(client_secrets_file: str, token_file: str) -> int:
    settings = get_google_drive_settings()
    try:
        destination = authorize_oauth_user(
            token_file,
            client_secrets_file=client_secrets_file,
            client_id=settings.google_drive_client_id,
            client_secret=settings.google_drive_client_secret,
        )
    except CredentialLoadError as exc:
        print(f"autorização falhou: {exc}", file=sys.stderr)
        return 1
    print("autorização OAuth User concluída")
    print(f"credencial salva em: {destination}")
    print("proteção do arquivo: somente o usuário atual (modo 0600)")
    print("próximo passo: configure GOOGLE_DRIVE_AUTH_MODE=oauth_user e ")
    print(f"GOOGLE_DRIVE_OAUTH_USER_FILE={destination}")
    return 0


async def _bootstrap_provider(settings) -> int:
    provider = GoogleDriveStorageProvider(settings)
    try:
        status = await provider.bootstrap()
    finally:
        await provider.aclose()
    print(f"status: {status.status.value}")
    print(f"root_folder_id: {status.root_folder_id}")
    print(f"root_state_file: {settings.root_state_path}")
    print(f"árvore oficial: {len(status.tree.found)}/18 pastas")
    return 0 if status.status.value == "connected" else 1


def _bootstrap(args) -> int:
    base = get_google_drive_settings()
    token_text = args.token_file or base.google_drive_oauth_user_file
    if not token_text:
        print(
            "bootstrap exige --token-file ou GOOGLE_DRIVE_OAUTH_USER_FILE",
            file=sys.stderr,
        )
        return 1
    token_path = Path(token_text).expanduser().resolve()

    if args.reauthorize or not token_path.exists():
        try:
            authorize_oauth_user(
                str(token_path),
                client_secrets_file=args.client_secrets_file,
                client_id=base.google_drive_client_id,
                client_secret=base.google_drive_client_secret,
            )
        except CredentialLoadError as exc:
            print(f"autorização falhou: {exc}", file=sys.stderr)
            return 1

    settings = base.model_copy(
        update={
            "google_drive_auth_mode": GoogleDriveAuthMode.OAUTH_USER,
            "google_drive_oauth_user_file": str(token_path),
            "google_drive_oauth_user_json": "",
            "google_drive_service_account_file": "",
            "google_drive_service_account_json": "",
        }
    )
    try:
        return asyncio.run(_bootstrap_provider(settings))
    except Exception as exc:  # noqa: BLE001 - CLI local; mensagem nunca contém token
        print(f"bootstrap falhou: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dhf-storage", description="CLI do Storage (Google Drive)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="verifica conexão e a árvore oficial de pastas")
    authorize_parser = subparsers.add_parser(
        "authorize", help="autoriza uma conta My Drive via OAuth Desktop App"
    )
    authorize_parser.add_argument(
        "--client-secrets-file",
        default="",
        help="JSON do OAuth Client do tipo Desktop app baixado do Google Cloud",
    )
    authorize_parser.add_argument(
        "--token-file",
        required=True,
        help="destino fora do Git para a credencial OAuth User durável",
    )
    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="autoriza se necessário e cria/recupera a root e as 18 pastas oficiais",
    )
    bootstrap_parser.add_argument(
        "--client-secrets-file",
        default="",
        help="JSON do OAuth Client Desktop; opcional quando CLIENT_ID/CLIENT_SECRET estão no env",
    )
    bootstrap_parser.add_argument(
        "--token-file",
        default="",
        help="destino da credencial; pode vir de GOOGLE_DRIVE_OAUTH_USER_FILE",
    )
    bootstrap_parser.add_argument(
        "--reauthorize",
        action="store_true",
        help="força novo consentimento mesmo se o token já existir",
    )

    args = parser.parse_args()

    if args.command == "check":
        sys.exit(asyncio.run(_check()))
    if args.command == "authorize":
        sys.exit(_authorize(args.client_secrets_file, args.token_file))
    if args.command == "bootstrap":
        sys.exit(_bootstrap(args))


if __name__ == "__main__":
    main()
