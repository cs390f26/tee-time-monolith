import importlib
import pytest
import tee_time.settings as settings


def test_settings_defaults(monkeypatch):
    """Verify ensure_settings succeeds when DATABASE_PATH is configured."""
    monkeypatch.setenv("DATABASE_PATH", "/tmp/test_tee_time.db")
    importlib.reload(settings)

    config = settings.ensure_settings()
    assert config["DATABASE_PATH"] == "/tmp/test_tee_time.db"


def test_settings_missing_required_env(monkeypatch):
    """Verify ensure_settings raises RuntimeError when DATABASE_PATH is missing."""
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    importlib.reload(settings)

    with pytest.raises(RuntimeError, match="Missing required settings"):
        settings.ensure_settings()