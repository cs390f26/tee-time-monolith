import pytest

from tee_time import settings


def test_settings_defaults(monkeypatch):
    """Verify ensure_settings succeeds and defaults MYSQL_PORT to 3306."""
    monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
    monkeypatch.setenv("MYSQL_USER", "tee_time")
    monkeypatch.setenv("MYSQL_PASSWORD", "tee_time")
    monkeypatch.setenv("MYSQL_DATABASE", "tee_time")
    monkeypatch.delenv("MYSQL_PORT", raising=False)
    monkeypatch.setattr(settings, "load_dotenv", lambda *args, **kwargs: None)

    config = settings.ensure_settings()
    assert config["MYSQL_HOST"] == "127.0.0.1"
    assert config["MYSQL_PORT"] == "3306"
    assert config["MYSQL_USER"] == "tee_time"
    assert config["MYSQL_PASSWORD"] == "tee_time"
    assert config["MYSQL_DATABASE"] == "tee_time"


def test_settings_missing_required_env(monkeypatch):
    """Verify ensure_settings raises RuntimeError when a MySQL setting is missing."""
    for name in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "load_dotenv", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="Missing required settings"):
        settings.ensure_settings()
