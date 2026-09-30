from datetime import date
import pytest

from tee_time.db import (
    ClubStorage,
    DatabaseUnavailableError,
    MemberAlreadyExistsError,
    PlayerAlreadyBookedError,
    PositionTakenError,
    SlotFullError,
)
from tee_time.types import MemberData, PlayerData


def test_ping_and_schema_creation(temp_db):
    temp_db.ping()


def test_ping_raises_when_table_missing(tmp_path):
    empty_db_path = tmp_path / "empty.db"
    storage = ClubStorage(str(empty_db_path))
    with pytest.raises(DatabaseUnavailableError):
        storage.ping()


def test_add_and_get_member(temp_db):
    member = MemberData(id="mem_01", name="Alice Smith", phone="555-0100")
    temp_db.add_member(member)

    fetched = temp_db.get_member("mem_01")
    assert fetched == member

    members = temp_db.list_members()
    assert len(members) == 1
    assert members[0].name == "Alice Smith"


def test_get_nonexistent_member(temp_db):
    assert temp_db.get_member("unknown_member") is None


def test_add_duplicate_member_raises(temp_db):
    member = MemberData(id="mem_01", name="Alice Smith", phone="555-0100")
    temp_db.add_member(member)

    with pytest.raises(MemberAlreadyExistsError):
        temp_db.add_member(member)


def test_add_player_to_slot(temp_db):
    member = MemberData(id="mem_01", name="Alice Smith", phone="555-0100")
    temp_db.add_member(member)

    target_date = date(2026, 9, 19)
    player = PlayerData(number=1, member_id="mem_01", name="Alice Smith")

    slot = temp_db.add_player(target_date, "07:00", player)

    assert slot.date == "2026-09-19"
    assert slot.time == "07:00"
    assert len(slot.players) == 1
    assert slot.players[0].member_id == "mem_01"


def test_get_tee_time_and_list_booked(temp_db):
    target_date = date(2026, 9, 19)
    assert temp_db.get_tee_time(target_date, "07:00") is None

    member = MemberData(id="mem_01", name="Alice", phone="555-0100")
    temp_db.add_member(member)
    player = PlayerData(number=1, member_id="mem_01", name="Alice")

    temp_db.add_player(target_date, "07:00", player)

    slot = temp_db.get_tee_time(target_date, "07:00")
    assert slot is not None
    assert slot.time == "07:00"

    booked_slots = temp_db.list_booked()
    assert len(booked_slots) == 1


def test_add_player_position_taken(temp_db):
    m1 = MemberData(id="mem_01", name="Alice", phone="555-0100")
    m2 = MemberData(id="mem_02", name="Bob", phone="555-0200")
    temp_db.add_member(m1)
    temp_db.add_member(m2)

    target_date = date(2026, 9, 19)
    p1 = PlayerData(number=1, member_id="mem_01", name="Alice")
    p2 = PlayerData(number=1, member_id="mem_02", name="Bob")

    temp_db.add_player(target_date, "07:00", p1)

    with pytest.raises(PositionTakenError):
        temp_db.add_player(target_date, "07:00", p2)


def test_add_player_already_booked(temp_db):
    m1 = MemberData(id="mem_01", name="Alice", phone="555-0100")
    temp_db.add_member(m1)

    target_date = date(2026, 9, 19)
    p1 = PlayerData(number=1, member_id="mem_01", name="Alice")
    p2 = PlayerData(number=2, member_id="mem_01", name="Alice")

    temp_db.add_player(target_date, "07:00", p1)

    with pytest.raises(PlayerAlreadyBookedError):
        temp_db.add_player(target_date, "07:00", p2)


def test_add_player_foursome_full(temp_db):
    target_date = date(2026, 9, 19)
    for i in range(1, 5):
        m_id = f"mem_0{i}"
        temp_db.add_member(MemberData(id=m_id, name=f"Player {i}", phone="555-0000"))
        temp_db.add_player(
            target_date,
            "07:00",
            PlayerData(number=i, member_id=m_id, name=f"Player {i}"),
        )

    temp_db.add_member(MemberData(id="mem_05", name="Player 5", phone="555-0000"))
    with pytest.raises(SlotFullError):
        temp_db.add_player(
            target_date,
            "07:00",
            PlayerData(number=1, member_id="mem_05", name="Player 5"),
        )


def test_database_unavailable_error_handling(tmp_path):
    invalid_dir = tmp_path / "invalid_path" / "db.sqlite"
    bad_storage = ClubStorage(str(invalid_dir))
    
    with pytest.raises(DatabaseUnavailableError):
        bad_storage.list_members()