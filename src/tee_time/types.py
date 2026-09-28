"""Stored records and the page views built from them.

The store returns MemberData and TeeTimeData. The application turns those
into the smaller shapes a page needs. The API serializes the views.
"""

from dataclasses import dataclass
from datetime import date, datetime

MAX_PLAYERS = 4


@dataclass(frozen=True)
class MemberData:
    """A member as stored."""

    id: str
    name: str
    phone: str


@dataclass(frozen=True)
class PlayerData:
    """One player already on a tee time."""

    number: int
    member_id: str
    name: str


@dataclass(frozen=True)
class TeeTimeData:
    """A tee time as stored, including an empty slot. Players are in number order."""

    date: str
    time: str
    players: tuple[PlayerData, ...]


@dataclass(frozen=True)
class MemberView:
    """Name and phone for the members page and the booking picker."""

    id: str
    name: str
    phone: str


@dataclass(frozen=True)
class TeeTimeSlot:
    """A card on the week grid, or one row on the reserved page."""

    id: str
    date: str
    time: str
    player_names: tuple[str, ...]
    player_count: int
    bookable: bool


@dataclass(frozen=True)
class TeeTimeView:
    """The book page: who is playing, then who can still be picked."""

    id: str
    date: str
    time: str
    players: tuple[PlayerData, ...]
    player_count: int
    bookable: bool
    available_members: tuple[MemberView, ...]


def slot_id(slot_date: str, slot_time: str) -> str:
    """Public tee time id, YYYY-MM-DDTHH:MM:00."""
    return f"{slot_date}T{slot_time}:00"


def slot_start(slot_date: str, slot_time: str, now: datetime) -> datetime:
    """The slot's start on the club's local clock."""
    hour, minute = (int(part) for part in slot_time.split(":", 1))
    day = date.fromisoformat(slot_date)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=now.tzinfo)


def bookable(player_count: int, slot_date: str, slot_time: str, now: datetime) -> bool:
    """True when the slot has an open seat and has not started yet."""
    return player_count < MAX_PLAYERS and slot_start(slot_date, slot_time, now) >= now


def member_view(member: MemberData) -> MemberView:
    """Copy the fields the members page shows."""
    return MemberView(id=member.id, name=member.name, phone=member.phone)


def _ordered(players: tuple[PlayerData, ...]) -> tuple[PlayerData, ...]:
    return tuple(sorted(players, key=lambda player: player.number))


def tee_time_slot(slot: TeeTimeData, now: datetime) -> TeeTimeSlot:
    """Card fields: time, names in player order, and whether it can be booked."""
    players = _ordered(slot.players)
    count = len(players)
    return TeeTimeSlot(
        id=slot_id(slot.date, slot.time),
        date=slot.date,
        time=slot.time,
        player_names=tuple(player.name for player in players),
        player_count=count,
        bookable=bookable(count, slot.date, slot.time, now),
    )


def tee_time_view(
    slot: TeeTimeData, members: list[MemberData], now: datetime
) -> TeeTimeView:
    """Book-page fields. available_members is the roster minus anyone already playing."""
    players = _ordered(slot.players)
    booked = {player.member_id for player in players}
    available = [
        member_view(member) for member in members if member.id not in booked
    ]
    available.sort(key=lambda member: (member.name.casefold(), member.id))
    count = len(players)
    return TeeTimeView(
        id=slot_id(slot.date, slot.time),
        date=slot.date,
        time=slot.time,
        players=players,
        player_count=count,
        bookable=bookable(count, slot.date, slot.time, now),
        available_members=tuple(available),
    )
