"""Unit tests for settings/config normalization."""

from __future__ import annotations

from app.core.config import Settings


def _settings(**kwargs) -> Settings:
    # _env_file=None -> ignore any local .env so tests are hermetic.
    return Settings(_env_file=None, **kwargs)


def test_async_url_from_postgresql_scheme():
    s = _settings(database_url="postgresql://u:p@host:5432/db")
    assert s.async_database_url == "postgresql+asyncpg://u:p@host:5432/db"


def test_async_url_from_postgres_scheme():
    s = _settings(database_url="postgres://u:p@host:5432/db")
    assert s.async_database_url == "postgresql+asyncpg://u:p@host:5432/db"


def test_async_url_passthrough():
    url = "postgresql+asyncpg://u:p@host:5432/db"
    assert _settings(database_url=url).async_database_url == url


def test_database_not_configured_by_default():
    s = _settings()
    assert s.database_configured is False
    assert s.async_database_url == ""


def test_kronos_defaults():
    s = _settings()
    assert s.kronos_model_id == "NeoQuasar/Kronos-small"
    assert s.kronos_tokenizer_id == "NeoQuasar/Kronos-Tokenizer-base"
    assert s.default_forecaster == "kronos"
