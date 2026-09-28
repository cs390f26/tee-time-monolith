"""SQLite storage for members and tee times.

Maps rows to MemberData and TeeTimeData. sqlite3 errors become storage
exceptions so the application layer does not import sqlite3.
"""

import sqlite3
from datetime import date
from pathlib import Path

from tee_time.store import (
    DatabaseUnavailableError,
    MemberAlreadyExistsError,
    PlayerAlreadyBookedError,
    PositionTakenError,
    SlotFullError,
)
from tee_time.types import MAX_PLAYERS, MemberData, PlayerData, TeeTimeData

_SCHEMA = Path(__file__).resolve().parents[2] / "scripts" / "schema.sql"


class ClubStorage:
    """ClubStore backed by a SQLite file."""

    def __init__(self, path: str):
        self._path = path

    def create_schema(self) -> None:
        """Create members, tee times, and bookings if they are not there yet."""
        creates = []
        for statement in _SCHEMA.read_text().split(";"):
            text = statement.strip()
            if text.upper().startswith("CREATE TABLE"):
                creates.append(text.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1))
        try:
            with self._connect() as conn:
                for statement in creates:
                    conn.execute(statement)
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc

    def ping(self) -> None:
        """Raise DatabaseUnavailableError when the file or members table is missing."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'members'"
                ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc
        if row is None:
            raise DatabaseUnavailableError("members table missing")

    def list_members(self) -> list[MemberData]:
        try:
            with self._connect() as conn:
                rows = conn.execute("SELECT id, name, phone FROM members").fetchall()
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc
        return [MemberData(id=row["id"], name=row["name"], phone=row["phone"]) for row in rows]

    def get_member(self, member_id: str) -> MemberData | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id, name, phone FROM members WHERE id = ?",
                    (member_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc
        if row is None:
            return None
        return MemberData(id=row["id"], name=row["name"], phone=row["phone"])

    def add_member(self, member: MemberData) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO members (id, name, phone) VALUES (?, ?, ?)",
                    (member.id, member.name, member.phone),
                )
        except sqlite3.IntegrityError as exc:
            raise MemberAlreadyExistsError(f"member {member.id} already exists") from exc
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc

    def list_tee_times(self, day: date) -> list[TeeTimeData]:
        return self._slots("t.slot_date = ?", (day.isoformat(),))

    def list_booked(self) -> list[TeeTimeData]:
        return [
            slot
            for slot in self._slots("1 = 1", ())
            if slot.players
        ]

    def get_tee_time(self, day: date, slot_time: str) -> TeeTimeData | None:
        slots = self._slots(
            "t.slot_date = ? AND substr(t.slot_time, 1, 5) = ?",
            (day.isoformat(), _hhmm(slot_time)),
        )
        return slots[0] if slots else None

    def add_player(self, day: date, slot_time: str, player: PlayerData) -> TeeTimeData:
        day_text = day.isoformat()
        hhmm = _hhmm(slot_time)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT id FROM tee_times
                WHERE slot_date = ? AND substr(slot_time, 1, 5) = ?
                """,
                (day_text, hhmm),
            ).fetchone()
            if row is None:
                cursor = conn.execute(
                    "INSERT INTO tee_times (slot_date, slot_time) VALUES (?, ?)",
                    (day_text, f"{hhmm}:00"),
                )
                tee_time_id = cursor.lastrowid
            else:
                tee_time_id = row["id"]
            players = _players(conn, tee_time_id)
            if len(players) >= MAX_PLAYERS:
                raise SlotFullError("foursome full")
            if any(existing.member_id == player.member_id for existing in players):
                raise PlayerAlreadyBookedError("already booked on this slot")
            if player.number < 1 or player.number > MAX_PLAYERS:
                raise PositionTakenError(f"player number {player.number} is not open")
            if any(existing.number == player.number for existing in players):
                raise PositionTakenError(f"player number {player.number} is taken")
            conn.execute(
                """
                INSERT INTO bookings (tee_time_id, member_id, player_position)
                VALUES (?, ?, ?)
                """,
                (tee_time_id, player.member_id, player.number),
            )
            conn.commit()
        except (SlotFullError, PlayerAlreadyBookedError, PositionTakenError):
            conn.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise _from_integrity(exc) from exc
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseUnavailableError("database not reachable") from exc
        finally:
            conn.close()
        updated = self.get_tee_time(day, hhmm)
        if updated is None:
            raise DatabaseUnavailableError("database not reachable")
        return updated

    def _slots(self, where: str, params: tuple) -> list[TeeTimeData]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT t.slot_date, t.slot_time, b.player_position, b.member_id, m.name
                    FROM tee_times t
                    LEFT JOIN bookings b ON b.tee_time_id = t.id
                    LEFT JOIN members m ON m.id = b.member_id
                    WHERE {where}
                    ORDER BY t.slot_date, t.slot_time, b.player_position
                    """,
                    params,
                ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc
        grouped: dict[tuple[str, str], list[PlayerData]] = {}
        for row in rows:
            key = (row["slot_date"], _hhmm(row["slot_time"]))
            grouped.setdefault(key, [])
            if row["member_id"] is not None:
                grouped[key].append(
                    PlayerData(
                        number=row["player_position"],
                        member_id=row["member_id"],
                        name=row["name"],
                    )
                )
        return [
            TeeTimeData(date=slot_date, time=slot_time, players=tuple(players))
            for (slot_date, slot_time), players in grouped.items()
        ]

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self._path)
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def _players(conn: sqlite3.Connection, tee_time_id: int) -> list[PlayerData]:
    rows = conn.execute(
        """
        SELECT b.player_position, b.member_id, m.name
        FROM bookings b
        JOIN members m ON m.id = b.member_id
        WHERE b.tee_time_id = ?
        ORDER BY b.player_position
        """,
        (tee_time_id,),
    ).fetchall()
    return [
        PlayerData(number=row["player_position"], member_id=row["member_id"], name=row["name"])
        for row in rows
    ]


def _hhmm(value: str) -> str:
    return value[:5]


def _from_integrity(exc: sqlite3.IntegrityError) -> Exception:
    message = str(exc)
    if "members.id" in message:
        return MemberAlreadyExistsError(message)
    if "member_id" in message:
        return PlayerAlreadyBookedError("already booked on this slot")
    if "player_position" in message or "CHECK constraint" in message:
        return PositionTakenError(message)
    return DatabaseUnavailableError("database not reachable")
