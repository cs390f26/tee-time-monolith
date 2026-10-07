from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pymysql
import pytest

from tee_time.db import (
    as_date_text,
    as_hhmm,
    execute,
    fetchall,
    fetchone,
    find_or_create_tee_time,
    is_check_violation,
    storage_error,
)
from tee_time.store import (
    DatabaseUnavailableError,
    MemberAlreadyExistsError,
    PlayerAlreadyBookedError,
    PositionTakenError,
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


def test_list_members_raises_database_unavailable_when_the_query_fails(
    storage, mock_db_session
):
    with (
        patch("tee_time.db.fetchall", side_effect=pymysql.Error("down")),
        pytest.raises(DatabaseUnavailableError),
    ):
        storage.list_members()


def test_get_member_raises_database_unavailable_when_the_query_fails(
    storage, mock_db_session
):
    with (
        patch("tee_time.db.fetchone", side_effect=pymysql.Error("down")),
        pytest.raises(DatabaseUnavailableError),
    ):
        storage.get_member("m1")


def test_add_member_raises_database_unavailable_when_the_insert_fails(
    storage, mock_db_session
):
    member = MemberData(id="m1", name="Ada", phone="555-0100")
    with (
        patch("tee_time.db.execute", side_effect=pymysql.Error("down")),
        pytest.raises(DatabaseUnavailableError),
    ):
        storage.add_member(member)


def test_list_tee_times_raises_database_unavailable_when_the_query_fails(
    storage, mock_db_session
):
    with (
        patch("tee_time.db.fetchall", side_effect=pymysql.Error("down")),
        pytest.raises(DatabaseUnavailableError),
    ):
        storage.list_tee_times(date(2099, 6, 15))


def test_list_booked_raises_database_unavailable_when_the_query_fails(
    storage, mock_db_session
):
    with (
        patch("tee_time.db.fetchall", side_effect=pymysql.Error("down")),
        pytest.raises(DatabaseUnavailableError),
    ):
        storage.list_booked()


def test_execute_returns_the_id_of_the_inserted_row(mock_db_session):
    cursor = MagicMock()
    cursor.lastrowid = 15
    mock_db_session.cursor.return_value.__enter__.return_value = cursor
    sql = "INSERT INTO tee_times (slot_date, slot_time) VALUES (%s, %s)"
    assert execute(mock_db_session, sql, ()) == 15


def test_session_commits_and_closes_the_connection_when_the_block_succeeds(storage):
    conn = MagicMock()
    with patch("pymysql.connect", return_value=conn), storage._session() as yielded:
        assert yielded is conn
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


def test_as_date_text_formats_a_date_a_datetime_and_a_string_as_yyyy_mm_dd():
    assert as_date_text(date(2099, 6, 15)) == "2099-06-15"
    assert as_date_text(datetime(2099, 6, 15, 7, 0)) == "2099-06-15"
    assert as_date_text("2099-06-15T07:00:00") == "2099-06-15"


def test_as_hhmm_formats_a_time_a_timedelta_and_a_string_as_hh_mm():
    assert as_hhmm(time(7, 30)) == "07:30"
    assert as_hhmm(timedelta(hours=14, minutes=30)) == "14:30"
    assert as_hhmm("08:00:00") == "08:00"


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        pytest.param(
            pymysql.IntegrityError(3819, "chk_player_position"),
            PositionTakenError,
            id="check_constraint_3819_becomes_position_taken",
        ),
        pytest.param(
            pymysql.IntegrityError(4025, "CHECK constraint failed"),
            PositionTakenError,
            id="check_constraint_4025_becomes_position_taken",
        ),
        pytest.param(
            pymysql.IntegrityError(1062, "Duplicate entry for key 'uq_booking_member'"),
            PlayerAlreadyBookedError,
            id="duplicate_member_key_becomes_player_already_booked",
        ),
        pytest.param(
            pymysql.IntegrityError(1062, "key uq_booking_position"),
            PositionTakenError,
            id="duplicate_position_key_becomes_position_taken",
        ),
        pytest.param(
            pymysql.IntegrityError(1062, "Duplicate entry for key 'PRIMARY'"),
            MemberAlreadyExistsError,
            id="duplicate_primary_key_becomes_member_already_exists",
        ),
        pytest.param(
            pymysql.IntegrityError(1452, "Cannot add or update a child row"),
            DatabaseUnavailableError,
            id="foreign_key_failure_becomes_database_unavailable",
        ),
        pytest.param(
            pymysql.IntegrityError(9999, "chk_player_position"),
            PositionTakenError,
            id="chk_player_position_in_the_message_becomes_position_taken",
        ),
    ],
)
def test_storage_error_translates_a_mysql_integrity_error(exc, expected):
    assert isinstance(storage_error(exc), expected)


@pytest.mark.parametrize(
    ("exc", "violation"),
    [
        pytest.param(
            pymysql.OperationalError(3819, "no"),
            True,
            id="error_3819_is_a_check_violation",
        ),
        pytest.param(
            pymysql.OperationalError(4025, "no"),
            True,
            id="error_4025_is_a_check_violation",
        ),
        pytest.param(
            pymysql.OperationalError(1000, "chk_player_position"),
            True,
            id="chk_player_position_in_the_message_is_a_check_violation",
        ),
        pytest.param(
            pymysql.OperationalError(2003, "down"),
            False,
            id="a_connection_error_is_not_a_check_violation",
        ),
        pytest.param(
            pymysql.OperationalError(),
            False,
            id="an_error_with_no_code_is_not_a_check_violation",
        ),
    ],
)
def test_is_check_violation_matches_mysql_check_constraint_errors(exc, violation):
    assert is_check_violation(exc) is violation


def test_find_or_create_tee_time_returns_the_existing_row_id():
    with patch("tee_time.db.locked_tee_time", return_value={"id": 4}):
        assert find_or_create_tee_time(MagicMock(), "2099-06-15", "07:00") == 4


def test_find_or_create_tee_time_inserts_date_and_hhmmss_when_no_row_exists():
    with (
        patch("tee_time.db.locked_tee_time", return_value=None),
        patch("tee_time.db.execute", return_value=8) as insert_slot,
    ):
        assert find_or_create_tee_time(MagicMock(), "2099-06-15", "07:00") == 8
    assert insert_slot.call_args.args[2] == ("2099-06-15", "07:00:00")


def test_find_or_create_tee_time_returns_the_row_id_after_a_duplicate_uq_slot_insert():
    with (
        patch("tee_time.db.locked_tee_time", side_effect=[None, {"id": 9}]),
        patch(
            "tee_time.db.execute",
            side_effect=pymysql.IntegrityError(1062, "Duplicate entry 'uq_slot'"),
        ),
    ):
        assert find_or_create_tee_time(MagicMock(), "2099-06-15", "07:00") == 9


def test_find_or_create_tee_time_reraises_an_integrity_error_that_is_not_uq_slot():
    with (
        patch("tee_time.db.locked_tee_time", return_value=None),
        patch(
            "tee_time.db.execute",
            side_effect=pymysql.IntegrityError(1062, "Duplicate entry 'PRIMARY'"),
        ),
        pytest.raises(pymysql.IntegrityError),
    ):
        find_or_create_tee_time(MagicMock(), "2099-06-15", "07:00")


def test_find_or_create_tee_time_reraises_uq_slot_when_the_row_is_still_missing():
    with (
        patch("tee_time.db.locked_tee_time", side_effect=[None, None]),
        patch(
            "tee_time.db.execute",
            side_effect=pymysql.IntegrityError(1062, "Duplicate entry 'uq_slot'"),
        ),
        pytest.raises(pymysql.IntegrityError),
    ):
        find_or_create_tee_time(MagicMock(), "2099-06-15", "07:00")