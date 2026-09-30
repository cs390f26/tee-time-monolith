from datetime import date
import pytest
from unittest.mock import MagicMock

from tee_time.tee_time import (
    NotFoundError,
    ServiceUnavailableError,
    TeeTimeApp,
    ValidationError,
)
from tee_time.types import MemberView, TeeTimeSlot, TeeTimeView


@pytest.fixture
def mock_storage():
    """Provides a mocked ClubStorage dependency."""
    return MagicMock()


@pytest.fixture
def app(mock_storage):
    """Provides a TeeTimeApp instance initialized with mock storage."""
    return TeeTimeApp(mock_storage)



def test_health_ok(app, mock_storage):
    app.health()
    mock_storage.ping.assert_called_once()


def test_health_raises_when_db_down(app, mock_storage):
    mock_storage.ping.side_effect = Exception("DB connection failed")
    with pytest.raises(ServiceUnavailableError):
        app.health()



def test_add_member_returns_id(app, mock_storage):
    mock_storage.save_member.return_value = "mem_101"
    
    member_id = app.add_member("Alice Smith", "555-0100")
    
    assert member_id == "mem_101"
    mock_storage.save_member.assert_called_once_with("Alice Smith", "555-0100")


@pytest.mark.parametrize(
    "name, phone",
    [
        ("", "555-0100"),            
        ("   ", "555-0100"),        
        ("Alice", ""),               
        ("Alice", "   "),            
        ("a" * 101, "555-0100"),     
    ],
)
def test_add_member_validation(app, name, phone):
    with pytest.raises(ValidationError):
        app.add_member(name, phone)



def test_list_tee_times(app, mock_storage):
    target_date = date(2026, 9, 19)
    sample_slot = TeeTimeSlot(
        id="2026-09-19T07:00:00",
        date="2026-09-19",
        time="07:00",
        player_names=["Alice"],
        player_count=1,
        bookable=True,
    )
    mock_storage.get_slots_for_day.return_value = [sample_slot]

    slots = app.list_tee_times(target_date)
    
    assert len(slots) == 1
    assert slots[0].id == "2026-09-19T07:00:00"
    mock_storage.get_slots_for_day.assert_called_once_with(target_date)


def test_get_tee_time_not_found(app, mock_storage):
    mock_storage.get_slot_view.return_value = None
    
    with pytest.raises(NotFoundError):
        app.get_tee_time(date(2026, 9, 19), "07:00")



def test_book_tee_time_success(app, mock_storage):
    target_date = date(2026, 9, 19)
    mock_view = TeeTimeView(
        id="2026-09-19T07:00:00",
        date="2026-09-19",
        time="07:00",
        players=[],
        player_count=1,
        bookable=True,
        available_members=[],
    )
    mock_storage.add_booking.return_value = mock_view

    result = app.book(target_date, "07:00", "mem_101")
    
    assert result == mock_view
    mock_storage.add_booking.assert_called_once_with(target_date, "07:00", "mem_101")


def test_book_tee_time_slot_not_found(app, mock_storage):
    mock_storage.add_booking.side_effect = NotFoundError("Tee time slot does not exist")
    
    with pytest.raises(NotFoundError):
        app.book(date(2026, 9, 19), "07:00", "mem_non_existent")


def test_book_tee_time_full_or_already_booked(app, mock_storage):
    mock_storage.add_booking.side_effect = ValidationError("Member already booked or slot full")
    
    with pytest.raises(ValidationError):
        app.book(date(2026, 9, 19), "07:00", "mem_101")