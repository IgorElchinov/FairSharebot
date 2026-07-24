from __future__ import annotations

import logging

import pytest

from fairsharebot.config import Settings
from fairsharebot.logging_conf import configure_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    # configure_logging mutates the shared root/named loggers; restore a
    # clean slate after each test so they don't leak into other tests.
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for name in ("fairsharebot", "httpx", "httpcore", "telegram"):
        logging.getLogger(name).setLevel(logging.NOTSET)


def test_configure_logging_creates_log_file_and_writes_to_it(settings):
    configure_logging(settings)
    logging.getLogger("fairsharebot.test").info("hello from a test")

    log_file = settings.log_dir / "fairsharebot.log"
    assert log_file.exists()
    assert "hello from a test" in log_file.read_text()


def test_configure_logging_quiets_noisy_third_party_loggers(settings):
    configure_logging(settings)

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    assert logging.getLogger("telegram").level == logging.WARNING


def test_verbose_mode_enables_activity_logs_but_not_third_party(db_path, tmp_path):
    settings = Settings(
        bot_token="test-token", db_path=db_path, log_level="DEBUG", log_dir=tmp_path / "logs"
    )

    configure_logging(settings)

    assert logging.getLogger("fairsharebot.activity").isEnabledFor(logging.DEBUG)
    assert logging.getLogger("fairsharebot.handlers.payment").isEnabledFor(logging.DEBUG)
    assert not logging.getLogger("httpx").isEnabledFor(logging.DEBUG)
    assert not logging.getLogger("httpcore").isEnabledFor(logging.DEBUG)
    assert not logging.getLogger("telegram.ext.Updater").isEnabledFor(logging.DEBUG)


def test_default_mode_keeps_fairsharebot_at_info(settings):
    configure_logging(settings)

    assert not logging.getLogger("fairsharebot.activity").isEnabledFor(logging.DEBUG)
    assert logging.getLogger("fairsharebot.activity").isEnabledFor(logging.INFO)
