from datetime import date, datetime, timezone
from unittest.mock import MagicMock
import pytest

from tee_time.store import (
    DatabaseUnavailableError,
    MemberAlreadyExistsError,
    PlayerAlreadyBookedError,
    PositionTakenError,
    SlotFullError,
    SlotNotFoundError,
)
from tee_time.tee_time import (
    NAME_MAX,
    PHONE_MAX,
    NotFoundError,
    ServiceUnavailableError,
    TeeTimeApp,
    ValidationError,
    checked_member,
    club_now,
    open_player_number,
    require_can_book,
    split_reserved,
)
from tee_time.types import MemberData, PlayerData, TeeTimeData, TeeTimeSlot, TeeTimeView


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.list_members.return_value = []
    store.list_tee_times.return_value = []
    return store


@pytest.fixture
def app(mock_store):
    return TeeTimeApp(store=mock_store)


# --- Health & Member Tests ---

def test_health_ok(app, mock_store):
    mock_store.ping.return_value = None
    app.health()
    mock_store.ping.assert_called_once()


def test_health_raises_service_unavailable(app, mock_store):
    mock_store.ping.side_effect = DatabaseUnavailableError("down")
    with pytest.raises(ServiceUnavailableError, match="database not reachable"):
        app.health()


def test_list_members_sorted(app, mock_store):
    m1 = MemberData(id="m1", name="Bob", phone="555-0100")
    m2 = MemberData(id="m2", name="alice", phone="555-0101")
    mock_store.list_members.return_value = [m1, m2]

    members = app.list_members()
    assert [m.name for m in members] == ["alice", "Bob"]


def test_add_member_success(app, mock_store):
    member_id = app.add_member("Alice Smith", "555-0100")
    assert isinstance(member_id, str)
    assert len(member_id) > 0
    mock_store.add_member.assert_called_once()


def test_add_member_collision_raises_service_unavailable(app, mock_store):
    mock_store.add_member.side_effect = MemberAlreadyExistsError("collision")
    with pytest.raises(ServiceUnavailableError, match="member id collision"):
        app.add_member("Alice Smith", "555-0100")


# --- Checked Member Validations ---

@pytest.mark.parametrize("name,phone,match", [
    ("", "555-0100", "name must not be blank"),
    ("Alice", "", "phone must not be blank"),
    ("A" * (NAME_MAX + 1), "555-0100", f"name must be at most {NAME_MAX}"),
    ("Alice", "5" * (PHONE_MAX + 1), f"phone must be at most {PHONE_MAX}"),
])
def test_checked_member_validation_errors(name, phone, match):
    with pytest.raises(ValidationError, match=match):
        checked_member(name, phone)


# --- List & Get Tee Times ---

def test_list_tee_times(app, mock_store):
    target_date = date(2026, 9, 19)
    now = datetime(2026, 9, 19, 6, 0, tzinfo=timezone.utc)
    slots = app.list_tee_times(target_date, now=now)
    assert len(slots) == 16
    assert isinstance(slots[0], TeeTimeSlot)


def test_get_tee_time_default_time_when_empty_in_store(app, mock_store):
    target_date = date(2026, 9, 19)
    now = datetime(2026, 9, 19, 6, 0, tzinfo=timezone.utc)
    mock_store.get_tee_time.return_value = None

    view = app.get_tee_time(target_date, "07:00", now=now)
    assert isinstance(view, TeeTimeView)
    assert view.time == "07:00"


def test_get_tee_time_not_found(app, mock_store):
    target_date = date(2026, 9, 19)
    mock_store.get_tee_time.return_value = None

    with pytest.raises(NotFoundError, match="tee time not found"):
        app.get_tee_time(target_date, "19:00")


# --- Booking Tests ---

def test_book_tee_time_success(app, mock_store):
    target_date = date(2026, 9, 19)
    now = datetime(2026, 9, 19, 6, 0, tzinfo=timezone.utc)
    slot_data = TeeTimeData(date="2026-09-19", time="07:00", players=())
    member_data = MemberData(id="m101", name="Alice", phone="555-0100")

    mock_store.get_tee_time.return_value = slot_data
    mock_store.get_member.return_value = member_data
    mock_store.add_player.return_value = TeeTimeData(
        date="2026-09-19",
        time="07:00",
        players=(PlayerData(number=1, member_id="m101", name="Alice"),),
    )

    view = app.book(target_date, "07:00", "m101", now=now)
    assert isinstance(view, TeeTimeView)
    assert view.player_count == 1


def test_book_tee_time_slot_not_found(app, mock_store):
    now = datetime(2026, 9, 19, 6, 0, tzinfo=timezone.utc)
    mock_store.get_tee_time.return_value = None

    with pytest.raises(NotFoundError, match="tee time not found"):
        app.book(date(2026, 9, 19), "19:00", "m101", now=now)


def test_book_tee_time_member_not_found(app, mock_store):
    now = datetime(2026, 9, 19, 6, 0, tzinfo=timezone.utc)
    slot_data = TeeTimeData(date="2026-09-19", time="07:00", players=())
    mock_store.get_tee_time.return_value = slot_data
    mock_store.get_member.return_value = None

    with pytest.raises(NotFoundError, match="member not found"):
        app.book(date(2026, 9, 19), "07:00", "m_nonexistent", now=now)


@pytest.mark.parametrize("exception_cls,match", [
    (SlotNotFoundError, "tee time not found"),
    (SlotFullError, "foursome full"),
    (PlayerAlreadyBookedError, "already booked on this slot"),
    (PositionTakenError, "foursome full"),
])
def test_save_player_storage_exceptions(app, mock_store, exception_cls, match):
    now = datetime(2026, 9, 19, 6, 0, tzinfo=timezone.utc)
    slot_data = TeeTimeData(date="2026-09-19", time="07:00", players=())
    member_data = MemberData(id="m101", name="Alice", phone="555-0100")

    mock_store.get_tee_time.return_value = slot_data
    mock_store.get_member.return_value = member_data
    mock_store.add_player.side_effect = exception_cls("error")

    with pytest.raises((ValidationError, NotFoundError), match=match):
        app.book(date(2026, 9, 19), "07:00", "m101", now=now)


# --- Booking Validation Helpers ---

def test_require_can_book_past_time():
    now = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)
    slot = TeeTimeData(date="2026-09-19", time="07:00", players=())
    member = MemberData(id="m1", name="Alice", phone="555-0100")

    with pytest.raises(ValidationError, match="tee time is in the past"):
        require_can_book(slot, member, now)


def test_open_player_number_full():
    players = tuple(
        PlayerData(number=i, member_id=f"m{i}", name=f"P{i}") for i in range(1, 5)
    )
    with pytest.raises(ValidationError, match="foursome full"):
        open_player_number(players)


# --- Reserved Slots & Clock Helpers ---

def test_list_reserved_splits_upcoming_and_past(app, mock_store):
    now = datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc)
    past_slot = TeeTimeData(date="2026-09-19", time="07:00", players=())
    upcoming_slot = TeeTimeData(date="2026-09-19", time="12:00", players=())
    mock_store.list_booked.return_value = [past_slot, upcoming_slot]

    upcoming, past = app.list_reserved(now=now)
    assert len(upcoming) == 1
    assert len(past) == 1
    assert upcoming[0].time == "12:00"
    assert past[0].time == "07:00"


def test_club_now_default():
    current = club_now(None)
    assert isinstance(current, datetime)