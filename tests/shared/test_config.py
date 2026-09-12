from urllib.parse import urlsplit

from dhf_shared.config import Settings


def test_database_urls_encode_reserved_credentials() -> None:
    settings = Settings(
        postgres_user="user@example.com",
        postgres_password="p@ss:/word#1",
        postgres_db="factory-db",
    )

    async_url = urlsplit(settings.database_url)
    sync_url = urlsplit(settings.database_url_sync)
    assert async_url.username == "user%40example.com"
    assert async_url.password == "p%40ss%3A%2Fword%231"
    assert sync_url.username == "user%40example.com"
    assert sync_url.password == "p%40ss%3A%2Fword%231"
