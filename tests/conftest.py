import os
from unittest.mock import MagicMock, patch

import pytest

from tee_time.app import create_app
from tee_time.db import ClubStorage

# Unit tests that talk to MySQL use this database, never the app database in .env.
TEST_DATABASE = "tee_time_test"


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


@pytest.fixture
def club_storage():
    """ClubStorage against tee_time_test, with empty tables for each test."""
    storage = ClubStorage(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "tee_time"),
        password=os.environ.get("MYSQL_PASSWORD", "tee_time"),
        database=TEST_DATABASE,
    )
    assert storage._database == TEST_DATABASE
    reset_test_database(storage)
    yield storage
    reset_test_database(storage)


def reset_test_database(storage: ClubStorage) -> None:
    """Drop the club tables and create them again. Does not touch other databases."""
    conn = storage._connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS bookings")
            cursor.execute("DROP TABLE IF EXISTS tee_times")
            cursor.execute("DROP TABLE IF EXISTS members")
        conn.commit()
    finally:
        conn.close()
    storage.create_schema()