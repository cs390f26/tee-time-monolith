from unittest.mock import MagicMock
import pytest

from tee_time.app import create_app
from tee_time.db import ClubStorage


@pytest.fixture
def mock_app():
    """Mock domain app for API tests."""
    return MagicMock()


@pytest.fixture
def client(mock_app):
    """Flask test client setup."""
    flask_app = create_app(mock_app)
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


@pytest.fixture
def temp_db(tmp_path):
    """Provides a fresh SQLite database instance in a temporary directory."""
    db_file = tmp_path / "test_club.db"
    storage = ClubStorage(str(db_file))

    if hasattr(storage, "create_tables"):
        storage.create_tables()
    elif hasattr(storage, "init_db"):
        storage.init_db()
    elif hasattr(storage, "_create_schema"):
        storage._create_schema()
    elif hasattr(storage, "create_schema"):
        storage.create_schema()

    storage.ping()
    return storage