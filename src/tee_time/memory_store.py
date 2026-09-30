"""In-memory ClubStore.

Data lasts for this process only. The SQLite store will replace this object
and keep the same methods. launch() starts with no members and no tee times.
"""

from datetime import date

from tee_time.store import (
    MemberAlreadyExistsError,
    PlayerAlreadyBookedError,
    PositionTakenError,
    SlotFullError,
)
from tee_time.types import (
    MAX_PLAYERS,
    MemberData,
    PlayerData,
    TeeTimeData,
    player_number,
)


class MemoryClubStore:
    """Members and tee times kept in dictionaries."""

    def __init__(
        self,
        members: list[MemberData] | None = None,
        tee_times: list[TeeTimeData] | None = None,
    ) -> None:
        self._members = {member.id: member for member in (members or [])}
        self._slots: dict[tuple[str, str], TeeTimeData] = {}
        for slot in tee_times or []:
            self._slots[(slot.date, slot.time)] = _ordered_slot(slot)

    def ping(self) -> None:
        """The process store is always reachable."""

    def list_members(self) -> list[MemberData]:
        return list(self._members.values())

    def get_member(self, member_id: str) -> MemberData | None:
        return self._members.get(member_id)

    def add_member(self, member: MemberData) -> None:
        if member.id in self._members:
            raise MemberAlreadyExistsError(f"member {member.id} already exists")
        self._members[member.id] = member

    def list_tee_times(self, day: date) -> list[TeeTimeData]:
        day_text = day.isoformat()
        return [slot for (slot_date, _), slot in self._slots.items() if slot_date == day_text]

    def list_booked(self) -> list[TeeTimeData]:
        return [slot for slot in self._slots.values() if slot.players]

    def get_tee_time(self, day: date, slot_time: str) -> TeeTimeData | None:
        return self._slots.get((day.isoformat(), slot_time))

    def add_player(self, day: date, slot_time: str, player: PlayerData) -> TeeTimeData:
        key = (day.isoformat(), slot_time)
        slot = self._slots.get(key)
        if slot is None:
            slot = TeeTimeData(date=key[0], time=slot_time, players=())
        if len(slot.players) >= MAX_PLAYERS:
            raise SlotFullError("foursome full")
        if any(existing.member_id == player.member_id for existing in slot.players):
            raise PlayerAlreadyBookedError("already booked on this slot")
        if player.number < 1 or player.number > MAX_PLAYERS:
            raise PositionTakenError(f"player number {player.number} is not open")
        if any(existing.number == player.number for existing in slot.players):
            raise PositionTakenError(f"player number {player.number} is taken")
        updated = _ordered_slot(
            TeeTimeData(
                date=slot.date,
                time=slot.time,
                players=(*slot.players, player),
            )
        )
        self._slots[key] = updated
        return updated


def _ordered_slot(slot: TeeTimeData) -> TeeTimeData:
    players = tuple(sorted(slot.players, key=player_number))
    return TeeTimeData(date=slot.date, time=slot.time, players=players)
