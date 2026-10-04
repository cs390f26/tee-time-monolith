import os
from unittest.mock import MagicMock

import pymysql
import pytest
from dotenv import load_dotenv

from tee_time.app import create_app
from tee_time.db import ClubStorage

TEST_DATABASE = "tee_time_test"


def mysql_connection_settings() -> dict:
    """Host, port, user, and password from .env. The database name stays separate."""
    load_dotenv()
    missing = [
        name
        for name in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD")
        if not os.environ.get(name)
    ]
    if missing:
        pytest.fail(
            "MySQL settings missing for tests. Set MYSQL_HOST, MYSQL_USER, "
            "and MYSQL_PASSWORD in .env. Missing: " + ", ".join(missing)
        )
    return {
        "host": os.environ["MYSQL_HOST"],
        "port": int(os.environ.get("MYSQL_PORT") or "3306"),
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
    }


def ensure_test_database(cfg: dict) -> None:
    """Create tee_time_test when the account is allowed to, then require access."""
    try:
        conn = pymysql.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            connect_timeout=5,
        )
    except pymysql.Error as exc:
        pytest.fail(f"MySQL is not reachable for tests: {exc}")
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{TEST_DATABASE}`")
        conn.commit()
    except pymysql.Error:
        conn.rollback()
    finally:
        conn.close()
    try:
        probe = pymysql.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            database=TEST_DATABASE,
            connect_timeout=5,
        )
    except pymysql.Error as exc:
        pytest.fail(
            "Cannot use database tee_time_test. Create it and grant the "
            f"MySQL user access. Details: {exc}"
        )
    probe.close()


def drop_tables(cfg: dict) -> None:
    conn = pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=TEST_DATABASE,
        connect_timeout=5,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS bookings")
            cursor.execute("DROP TABLE IF EXISTS tee_times")
            cursor.execute("DROP TABLE IF EXISTS members")
        conn.commit()
    finally:
        conn.close()


def test_storage(cfg: dict | None = None) -> ClubStorage:
    settings = cfg or mysql_connection_settings()
    return ClubStorage(database=TEST_DATABASE, **settings)


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
def empty_db():
    """tee_time_test with the tables dropped."""
    cfg = mysql_connection_settings()
    ensure_test_database(cfg)
    drop_tables(cfg)
    return test_storage(cfg)


@pytest.fixture
def temp_db():
    """Provides a fresh schema in the tee_time_test database."""
    cfg = mysql_connection_settings()
    ensure_test_database(cfg)
    drop_tables(cfg)
    storage = test_storage(cfg)
    storage.create_schema()
    storage.ping()
    return storage
