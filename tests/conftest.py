from unittest.mock import MagicMock, patch
import pytest

from tee_time.app import create_app
from tee_time.db import ClubStorage


# --- Flask App Fixtures ---
@pytest.fixture
def mock_tee_time_app():
    """Provides a mocked instance of TeeTimeApp."""
    return MagicMock()


@pytest.fixture
def app(mock_tee_time_app):
    """Creates a test Flask app instance using the create_app factory."""
    app = create_app(mock_tee_time_app)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Provides the Flask test client required by API tests."""
    return app.test_client()


# --- Database / Storage Fixtures ---
@pytest.fixture
def storage():
    """Returns a ClubStorage instance for unit testing."""
    return ClubStorage(
        host="localhost",
        port=3306,
        user="test_user",
        password="test_password",
        database="test_db",
    )


@pytest.fixture
def mock_db_session(storage):
    """Mocks the internal _session() context manager on ClubStorage."""
    with patch.object(storage, "_session") as mock_session:
        mock_conn = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_conn
        yield mock_conn