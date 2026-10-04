"""Storage contract for members and tee times.

ClubStorage in db.py implements this against MySQL. This module does not
import pymysql. Callers in the application layer translate these errors
into domain errors.
"""

from datetime import date
from typing import Protocol

from tee_time.types import MemberData, PlayerData, TeeTimeData


class DatabaseUnavailableError(Exception):
    """Raised when the store cannot be reached."""


class MemberAlreadyExistsError(Exception):
    """Raised when a member id is already stored."""


class SlotNotFoundError(Exception):
    """Raised when a tee time slot is not stored."""


class SlotFullError(Exception):
    """Raised when a slot already has four players."""


class PlayerAlreadyBookedError(Exception):
    """Raised when the member is already on the slot."""


class PositionTakenError(Exception):
    """Raised when that player number is already used."""


class ClubStore(Protocol):
    """Reads and writes the club's members and tee times."""

    def ping(self) -> None:
        """Raise DatabaseUnavailableError when the store cannot be reached."""

    def list_members(self) -> list[MemberData]:
        """Return every member. Order is not significant."""

    def get_member(self, member_id: str) -> MemberData | None:
        """Return one member, or None when the id is unknown."""

    def add_member(self, member: MemberData) -> None:
        """Store a member. Raise MemberAlreadyExistsError when the id is taken."""

    def list_tee_times(self, day: date) -> list[TeeTimeData]:
        """Return every slot on that day, including slots with no players."""

    def list_booked(self) -> list[TeeTimeData]:
        """Return slots that have at least one player."""

    def get_tee_time(self, day: date, slot_time: str) -> TeeTimeData | None:
        """Return one slot, or None when that date and time are not scheduled."""

    def add_player(self, day: date, slot_time: str, player: PlayerData) -> TeeTimeData:
        """Append one player and return the updated slot.

        A date and time that are not stored yet start as an empty slot.
        """
