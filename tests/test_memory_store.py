from datetime import date

import pytest

from tee_time.memory_store import MemoryClubStore
from tee_time.store import (
    MemberAlreadyExistsError,
    PlayerAlreadyBookedError,
    PositionTakenError,
    SlotFullError,
)
from tee_time.types import MemberData, PlayerData, TeeTimeData


def test_memory_store_member_crud():
    store = MemoryClubStore()
    store.ping()
    
    m = MemberData(id="m1", name="Alice", phone="555-0100")
    store.add_member(m)
    assert store.get_member("m1") == m
    assert len(store.list_members()) == 1

    with pytest.raises(MemberAlreadyExistsError):
        store.add_member(m)

def test_memory_store_tee_times():
    store = MemoryClubStore()
    today = date(2026, 9, 19)
    player = PlayerData(number=1, member_id="m1", name="Alice")
    
    slot = store.add_player(today, "08:00", player)
    assert len(slot.players) == 1
    assert len(store.list_booked()) == 1
    assert store.get_tee_time(today, "08:00") is not None
    assert len(store.list_tee_times(today)) == 1


def test_memory_store_sorts_loaded_players_into_number_order():
    stored = TeeTimeData(
        date="2026-10-07",
        time="08:00",
        players=(
            PlayerData(number=2, member_id="m2", name="Grace"),
            PlayerData(number=1, member_id="m1", name="Ada"),
        ),
    )
    store = MemoryClubStore(tee_times=[stored])
    slot = store.get_tee_time(date(2026, 10, 7), "08:00")
    assert [player.number for player in slot.players] == [1, 2]


def _store_with_ada_at_0800():
    return MemoryClubStore(
        tee_times=[
            TeeTimeData(
                date="2026-10-07",
                time="08:00",
                players=(PlayerData(number=1, member_id="m1", name="Ada"),),
            )
        ]
    )


def test_memory_store_raises_player_already_booked_when_the_member_is_on_the_slot():
    day = date(2026, 10, 7)
    store = _store_with_ada_at_0800()
    with pytest.raises(PlayerAlreadyBookedError):
        store.add_player(day, "08:00", PlayerData(number=2, member_id="m1", name="Ada"))


def test_memory_store_raises_position_taken_when_the_player_number_is_outside_1_to_4():
    day = date(2026, 10, 7)
    store = _store_with_ada_at_0800()
    with pytest.raises(PositionTakenError, match="is not open"):
        store.add_player(
            day, "08:00", PlayerData(number=0, member_id="m2", name="Grace")
        )


def test_memory_store_raises_position_taken_when_that_player_number_is_already_used():
    day = date(2026, 10, 7)
    store = _store_with_ada_at_0800()
    with pytest.raises(PositionTakenError, match="is taken"):
        store.add_player(
            day, "08:00", PlayerData(number=1, member_id="m2", name="Grace")
        )


def test_memory_store_raises_slot_full_when_four_players_are_already_booked():
    day = date(2026, 10, 7)
    full = MemoryClubStore(
        tee_times=[
            TeeTimeData(
                date="2026-10-07",
                time="09:00",
                players=tuple(
                    PlayerData(number=i, member_id=f"m{i}", name=f"P{i}")
                    for i in range(1, 5)
                ),
            )
        ]
    )
    with pytest.raises(SlotFullError):
        full.add_player(day, "09:00", PlayerData(number=1, member_id="m9", name="New"))