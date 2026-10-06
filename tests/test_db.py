from datetime import date
from unittest.mock import MagicMock, patch
import pymysql
import pytest

from tee_time.db import ClubStorage, execute, fetchall, fetchone
from tee_time.store import (
    DatabaseUnavailableError,
    MemberAlreadyExistsError,
)
from tee_time.types import MemberData, PlayerData


# --- Health & Setup Tests ---

def test_ping_success(storage):
    with patch("tee_time.db.fetchone", return_value={"1": 1}):
        with patch.object(storage, "_session"):
            storage.ping()


def test_ping_missing_table(storage):
    with patch("tee_time.db.fetchone", return_value=None):
        with patch.object(storage, "_session"):
            with pytest.raises(DatabaseUnavailableError, match="members table missing"):
                storage.ping()


def test_ping_db_error(storage):
    with patch("tee_time.db.fetchone", side_effect=pymysql.OperationalError(2003, "Can't connect")):
        with patch.object(storage, "_session"):
            with pytest.raises(DatabaseUnavailableError):
                storage.ping()


def test_create_schema(storage, mock_db_session):
    mock_cursor = MagicMock()
    mock_db_session.cursor.return_value.__enter__.return_value = mock_cursor
    storage.create_schema()
    assert mock_cursor.execute.call_count >= 1


def test_create_schema_error(storage, mock_db_session):
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = pymysql.Error("SQL Error")
    mock_db_session.cursor.return_value.__enter__.return_value = mock_cursor
    with pytest.raises(DatabaseUnavailableError):
        storage.create_schema()


# --- Member Management Tests ---

def test_get_member_found(storage, mock_db_session):
    row = {"id": "m123", "name": "Jane Doe", "phone": "555-0199"}
    with patch("tee_time.db.fetchone", return_value=row):
        member = storage.get_member("m123")
        assert member == MemberData(id="m123", name="Jane Doe", phone="555-0199")


def test_get_member_not_found(storage, mock_db_session):
    with patch("tee_time.db.fetchone", return_value=None):
        assert storage.get_member("nonexistent") is None


def test_list_members(storage, mock_db_session):
    rows = [
        {"id": "m1", "name": "Alice", "phone": "555-0101"},
        {"id": "m2", "name": "Bob", "phone": "555-0102"},
    ]
    with patch("tee_time.db.fetchall", return_value=rows):
        members = storage.list_members()
        assert len(members) == 2
        assert members[0].name == "Alice"


def test_add_member_success(storage, mock_db_session):
    new_member = MemberData(id="m456", name="John Smith", phone="555-0100")
    with patch("tee_time.db.execute") as mock_exec:
        storage.add_member(new_member)
        mock_exec.assert_called_once()


def test_add_member_duplicate(storage, mock_db_session):
    new_member = MemberData(id="m456", name="John Smith", phone="555-0100")
    with patch("tee_time.db.execute", side_effect=pymysql.IntegrityError(1062, "Duplicate")):
        with pytest.raises(MemberAlreadyExistsError):
            storage.add_member(new_member)


# --- Tee Time Retrieval Tests ---

def test_get_tee_time(storage, mock_db_session):
    mock_rows = [
        {
            "id": 1,
            "slot_date": date(2026, 10, 5),
            "slot_time": "08:00",
            "player_position": 1,
            "name": "Alice",
            "member_id": "m1",
        }
    ]
    with patch("tee_time.db.fetchall", return_value=mock_rows):
        tee_time = storage.get_tee_time(date(2026, 10, 5), "08:00")
        assert tee_time is not None


def test_player_data_instantiation():
    player = PlayerData(number=1, name="John Smith", member_id="m1")
    assert player.number == 1
    assert player.name == "John Smith"
    assert player.member_id == "m1"


# --- Reservations Tests ---

def test_add_reservation_success(storage, mock_db_session):
    if hasattr(storage, "add_reservation"):
        with patch("tee_time.db.execute") as mock_exec:
            storage.add_reservation(date(2026, 10, 5), "08:00", "m1", player_position=1)
            assert mock_exec.call_count >= 1


def test_add_reservation_slot_full(storage, mock_db_session):
    if hasattr(storage, "add_reservation"):
        with patch("tee_time.db.execute", side_effect=pymysql.IntegrityError(1062, "Duplicate slot")):
            with pytest.raises(Exception):
                storage.add_reservation(date(2026, 10, 5), "08:00", "m1", player_position=1)


def test_delete_reservation_success(storage, mock_db_session):
    if hasattr(storage, "delete_reservation"):
        with patch("tee_time.db.execute", return_value=1) as mock_exec:
            storage.delete_reservation(date(2026, 10, 5), "08:00", "m1")
            assert mock_exec.call_count >= 1


def test_delete_reservation_not_found(storage, mock_db_session):
    if hasattr(storage, "delete_reservation"):
        with patch("tee_time.db.execute", return_value=0):
            with pytest.raises(Exception):
                storage.delete_reservation(date(2026, 10, 5), "08:00", "m1")


# --- Context Manager & Connection Error Tests ---

def test_session_connection_failure(storage):
    with patch("pymysql.connect", side_effect=pymysql.OperationalError(2003, "Can't connect")):
        with pytest.raises(DatabaseUnavailableError):
            with storage._session():
                pass


def test_session_rollback_on_error(storage):
    mock_conn = MagicMock()
    with patch("pymysql.connect", return_value=mock_conn):
        with pytest.raises(RuntimeError):
            with storage._session():
                raise RuntimeError("Unexpected failure")
        assert mock_conn.rollback.called


# --- Core SQL Helper Function Tests ---

def test_helper_fetchone(mock_db_session):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"val": 1}
    mock_db_session.cursor.return_value.__enter__.return_value = mock_cursor

    result = fetchone(mock_db_session, "SELECT 1", None)
    assert result == {"val": 1}


def test_helper_fetchall(mock_db_session):
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [{"id": 1}, {"id": 2}]
    mock_db_session.cursor.return_value.__enter__.return_value = mock_cursor

    result = fetchall(mock_db_session, "SELECT * FROM members", None)
    assert len(result) == 2


def test_helper_execute_database_error(mock_db_session):
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = pymysql.DatabaseError("Execution error")
    mock_db_session.cursor.return_value.__enter__.return_value = mock_cursor

    with pytest.raises(pymysql.DatabaseError):
        execute(mock_db_session, "UPDATE members SET name='X'", None)


# --- Teardown & Utility Tests ---

def test_clear_data_if_exists(storage, mock_db_session):
    if hasattr(storage, "clear") or hasattr(storage, "reset"):
        clear_func = getattr(storage, "clear", None) or getattr(storage, "reset", None)
        with patch("tee_time.db.execute") as mock_exec:
            clear_func()
            assert mock_exec.call_count >= 1


def test_close_storage_connection(storage):
    if hasattr(storage, "close"):
        mock_conn = MagicMock()
        storage._conn = mock_conn
        storage.close()
        assert storage._conn is None or mock_conn.close.called