"""Club rules: members, tee time listings, and booking.

Construct with a ClubStore. HTTP parsing stays in the API.
"""

import secrets
from datetime import date, datetime, timezone

from tee_time.store import (
    ClubStore,
    DatabaseUnavailableError,
    MemberAlreadyExistsError,
    PlayerAlreadyBookedError,
    PositionTakenError,
    SlotFullError,
    SlotNotFoundError,
)
from tee_time.types import (
    MAX_PLAYERS,
    MemberData,
    MemberView,
    PlayerData,
    TeeTimeData,
    TeeTimeSlot,
    TeeTimeView,
    member_view,
    slot_start,
    tee_time_slot,
    tee_time_view,
)

NAME_MAX = 100
PHONE_MAX = 20
# Sixteen times, four columns by four rows: 7:00 through 2:30, every 30 minutes.
DEFAULT_TIMES = tuple(
    f"{(7 * 60 + offset) // 60:02d}:{(7 * 60 + offset) % 60:02d}"
    for offset in range(0, 16 * 30, 30)
)


class ValidationError(Exception):
    """Raised when input breaks a club rule. Nothing was written."""


class NotFoundError(Exception):
    """Raised when a member or tee time does not exist."""


class ServiceUnavailableError(Exception):
    """Raised when the store cannot be reached.

    Wraps storage failures so the API does not import tee_time.store.
    """


class TeeTimeApp:
    """Application logic for the club. Construct with a ClubStore."""

    def __init__(self, store: ClubStore):
        self._store = store

    def health(self) -> None:
        """Check that the store is reachable.

        Raises ServiceUnavailableError when it is not.
        """
        self._call(self._store.ping)

    def list_members(self) -> list[MemberView]:
        """Return every member, sorted by name, then id."""
        members = self._members()
        members.sort(key=_member_order)
        return [member_view(member) for member in members]

    def add_member(self, name: str, phone: str) -> str:
        """Validate a name and phone, store the member, and return the new id."""
        name = name.strip()
        phone = phone.strip()
        if not name:
            raise ValidationError("name must not be blank")
        if not phone:
            raise ValidationError("phone must not be blank")
        if len(name) > NAME_MAX:
            raise ValidationError(f"name must be at most {NAME_MAX} characters")
        if len(phone) > PHONE_MAX:
            raise ValidationError(f"phone must be at most {PHONE_MAX} characters")

        member = MemberData(id=secrets.token_hex(4), name=name, phone=phone)
        try:
            self._store.add_member(member)
        except MemberAlreadyExistsError as exc:
            raise ServiceUnavailableError(
                "service unavailable: member id collision"
            ) from exc
        except DatabaseUnavailableError as exc:
            raise ServiceUnavailableError(
                "service unavailable: database not reachable"
            ) from exc
        return member.id

    def list_tee_times(
        self, day: date, now: datetime | None = None
    ) -> list[TeeTimeSlot]:
        """Return the sixteen default times for that day, earliest first.

        A time with no stored players is an empty slot. A time that has
        already started cannot be booked.
        """
        now = _now(now)
        return [tee_time_slot(slot, now) for slot in self._day_slots(day)]

    def get_tee_time(
        self, day: date, slot_time: str, now: datetime | None = None
    ) -> TeeTimeView:
        """Return one slot for the book page, or raise NotFoundError."""
        now = _now(now)
        slot = self._load_slot(day, slot_time)
        return tee_time_view(slot, self._members(), now)

    def list_reserved(
        self, now: datetime | None = None
    ) -> tuple[list[TeeTimeSlot], list[TeeTimeSlot]]:
        """Booked slots split into upcoming (soonest first) and past (most recent first)."""
        now = _now(now)
        try:
            booked = self._store.list_booked()
        except DatabaseUnavailableError as exc:
            raise ServiceUnavailableError(
                "service unavailable: database not reachable"
            ) from exc
        upcoming = [slot for slot in booked if slot_start(slot.date, slot.time, now) >= now]
        past = [slot for slot in booked if slot_start(slot.date, slot.time, now) < now]
        upcoming.sort(key=lambda slot: (slot.date, slot.time))
        past.sort(key=lambda slot: (slot.date, slot.time), reverse=True)
        return (
            [tee_time_slot(slot, now) for slot in upcoming],
            [tee_time_slot(slot, now) for slot in past],
        )

    def book(
        self,
        day: date,
        slot_time: str,
        member_id: str,
        now: datetime | None = None,
    ) -> TeeTimeView:
        """Add one member to a slot and return the updated book-page view.

        Unknown slot or member raises NotFoundError. A time that has already
        started, a full foursome, or a member already on the slot raises
        ValidationError. Nothing is written in those cases.
        """
        now = _now(now)
        slot = self._load_slot(day, slot_time)
        member = self._load_member(member_id)
        if slot_start(day.isoformat(), slot_time, now) < now:
            raise ValidationError("tee time is in the past")
        if len(slot.players) >= MAX_PLAYERS:
            raise ValidationError("foursome full")
        if any(player.member_id == member.id for player in slot.players):
            raise ValidationError("already booked on this slot")

        taken = {player.number for player in slot.players}
        number = next(n for n in range(1, MAX_PLAYERS + 1) if n not in taken)
        player = PlayerData(number=number, member_id=member.id, name=member.name)
        members = self._members()
        try:
            updated = self._store.add_player(day, slot_time, player)
        except SlotNotFoundError as exc:
            raise NotFoundError("tee time not found") from exc
        except SlotFullError as exc:
            raise ValidationError("foursome full") from exc
        except PlayerAlreadyBookedError as exc:
            raise ValidationError("already booked on this slot") from exc
        except PositionTakenError as exc:
            raise ValidationError("foursome full") from exc
        except DatabaseUnavailableError as exc:
            raise ServiceUnavailableError(
                "service unavailable: database not reachable"
            ) from exc
        return tee_time_view(updated, members, now)

    def _load_slot(self, day: date, slot_time: str) -> TeeTimeData:
        try:
            slot = self._store.get_tee_time(day, slot_time)
        except DatabaseUnavailableError as exc:
            raise ServiceUnavailableError(
                "service unavailable: database not reachable"
            ) from exc
        if slot is None and slot_time in DEFAULT_TIMES:
            return TeeTimeData(date=day.isoformat(), time=slot_time, players=())
        if slot is None:
            raise NotFoundError("tee time not found")
        return slot

    def _day_slots(self, day: date) -> list[TeeTimeData]:
        try:
            stored = self._store.list_tee_times(day)
        except DatabaseUnavailableError as exc:
            raise ServiceUnavailableError(
                "service unavailable: database not reachable"
            ) from exc
        by_time = {slot.time: slot for slot in stored}
        day_text = day.isoformat()
        return [
            by_time.get(slot_time)
            or TeeTimeData(date=day_text, time=slot_time, players=())
            for slot_time in DEFAULT_TIMES
        ]

    def _load_member(self, member_id: str) -> MemberData:
        try:
            member = self._store.get_member(member_id)
        except DatabaseUnavailableError as exc:
            raise ServiceUnavailableError(
                "service unavailable: database not reachable"
            ) from exc
        if member is None:
            raise NotFoundError("member not found")
        return member

    def _members(self) -> list[MemberData]:
        try:
            return self._store.list_members()
        except DatabaseUnavailableError as exc:
            raise ServiceUnavailableError(
                "service unavailable: database not reachable"
            ) from exc

    def _call(self, fn) -> None:
        try:
            fn()
        except DatabaseUnavailableError as exc:
            raise ServiceUnavailableError(
                "service unavailable: database not reachable"
            ) from exc


def _now(now: datetime | None) -> datetime:
    """Club-local clock. Pass now to freeze it."""
    if now is not None:
        return now
    return datetime.now(timezone.utc).astimezone()


def _member_order(member: MemberData) -> tuple[str, str]:
    return (member.name.casefold(), member.id)
