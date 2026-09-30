from datetime import datetime, timezone
import pytest

from tee_time.types import (
    MemberData,
    PlayerData,
    TeeTimeData,
    bookable,
    member_view,
    slot_id,
    slot_start,
    tee_time_slot,
    tee_time_view,
)


def test_slot_id_formatting():
    assert slot_id("2026-09-19", "07:00") == "2026-09-19T07:00:00"


def test_slot_start_parsing():
    now = datetime.now(timezone.utc)
    start_dt = slot_start("2026-09-19", "08:30", now)
    
    assert start_dt.year == 2026
    assert start_dt.month == 9
    assert start_dt.day == 19
    assert start_dt.hour == 8
    assert start_dt.minute == 30
    assert start_dt.tzinfo == now.tzinfo


def test_bookable_conditions():
    now = datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc)

    assert bookable(3, "2026-09-19", "11:00", now) is True

    assert bookable(1, "2026-09-19", "09:00", now) is False

    assert bookable(4, "2026-09-19", "11:00", now) is False


def test_member_view_conversion():
    member_data = MemberData(id="m1", name="Alice Smith", phone="555-0100")
    view = member_view(member_data)

    assert view.id == "m1"
    assert view.name == "Alice Smith"
    assert view.phone == "555-0100"


def test_tee_time_slot_conversion():
    now = datetime(2026, 9, 19, 6, 0, tzinfo=timezone.utc)
    slot_data = TeeTimeData(
        date="2026-09-19",
        time="07:00",
        players=(
            PlayerData(number=2, member_id="m2", name="Bob"),
            PlayerData(number=1, member_id="m1", name="Alice"),
        ),
    )

    slot = tee_time_slot(slot_data, now)

    assert slot.id == "2026-09-19T07:00:00"
    assert slot.player_names == ("Alice", "Bob")
    assert slot.player_count == 2
    assert slot.bookable is True


def test_tee_time_view_available_members_filtering():
    now = datetime(2026, 9, 19, 6, 0, tzinfo=timezone.utc)
    slot_data = TeeTimeData(
        date="2026-09-19",
        time="07:00",
        players=(PlayerData(number=1, member_id="m1", name="Alice"),),
    )
    all_members = [
        MemberData(id="m1", name="Alice", phone="555-0100"),
        MemberData(id="m2", name="Charlie", phone="555-0200"),
        MemberData(id="m3", name="Bob", phone="555-0300"),
    ]

    view = tee_time_view(slot_data, all_members, now)

    assert view.player_count == 1
    available_ids = [m.id for m in view.available_members]
    assert "m1" not in available_ids
    assert [m.name for m in view.available_members] == ["Bob", "Charlie"]