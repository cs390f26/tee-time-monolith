from datetime import date
import pytest
from tee_time.memory_store import MemoryClubStore
from tee_time.store import MemberAlreadyExistsError, SlotFullError
from tee_time.types import MemberData, PlayerData

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