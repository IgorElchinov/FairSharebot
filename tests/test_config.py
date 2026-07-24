from __future__ import annotations

import pytest

from fairsharebot.config import ConfigError, load_settings


def test_load_settings_requires_bot_token(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("")

    with pytest.raises(ConfigError):
        load_settings(env_file)


def test_load_settings_reads_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("BOT_TOKEN=test-token\nDB_PATH=./somewhere.sqlite3\n")

    settings = load_settings(env_file)

    assert settings.bot_token == "test-token"
    assert str(settings.db_path) == "somewhere.sqlite3"
    assert settings.log_level == "INFO"
