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
        try:
            with self._connect() as conn:
                for statement in create_table_statements():
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
        return [member_from_row(row) for row in rows]

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
        return member_from_row(row)

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
        return self.slots_on_day(day)

    def list_booked(self) -> list[TeeTimeData]:
        return self.booked_slots()

    def get_tee_time(self, day: date, slot_time: str) -> TeeTimeData | None:
        return self.slot_at(day, slot_time)

    def slots_on_day(self, day: date) -> list[TeeTimeData]:
        return self._load_tee_times(
            """
            SELECT id, slot_date, slot_time
            FROM tee_times
            WHERE slot_date = ?
            ORDER BY slot_time
            """,
            (day.isoformat(),),
        )

    def slot_at(self, day: date, slot_time: str) -> TeeTimeData | None:
        slots = self._load_tee_times(
            """
            SELECT id, slot_date, slot_time
            FROM tee_times
            WHERE slot_date = ? AND substr(slot_time, 1, 5) = ?
            """,
            (day.isoformat(), hour_and_minute(slot_time)),
        )
        if not slots:
            return None
        return slots[0]

    def booked_slots(self) -> list[TeeTimeData]:
        slots = self._load_tee_times(
            """
            SELECT id, slot_date, slot_time
            FROM tee_times
            ORDER BY slot_date, slot_time
            """,
            (),
        )
        return [slot for slot in slots if slot.players]

    def add_player(self, day: date, slot_time: str, player: PlayerData) -> TeeTimeData:
        day_text = day.isoformat()
        hhmm = hour_and_minute(slot_time)
        conn = self._connect()
        try:
            # One transaction so the seat check and the insert cannot interleave.
            conn.execute("BEGIN IMMEDIATE")
            tee_time_id = find_or_create_tee_time(conn, day_text, hhmm)
            reject_closed_seat(players_for(conn, tee_time_id), player)
            insert_booking(conn, tee_time_id, player)
            conn.commit()
        except (SlotFullError, PlayerAlreadyBookedError, PositionTakenError):
            conn.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise storage_error(exc) from exc
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseUnavailableError("database not reachable") from exc
        finally:
            conn.close()
        updated = self.slot_at(day, hhmm)
        if updated is None:
            raise DatabaseUnavailableError("database not reachable")
        return updated

    def _load_tee_times(self, sql: str, params: tuple) -> list[TeeTimeData]:
        try:
            with self._connect() as conn:
                rows = conn.execute(sql, params).fetchall()
                return [tee_time_from_row(conn, row) for row in rows]
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self._path)
        except sqlite3.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def create_table_statements() -> list[str]:
    """CREATE TABLE statements from schema.sql, safe to re-run.

    Drops stay out so startup does not wipe an existing database.
    """
    statements = []
    for statement in _SCHEMA.read_text().split(";"):
        text = statement.strip()
        if text.upper().startswith("CREATE TABLE"):
            statements.append(
                text.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1)
            )
    return statements


def member_from_row(row: sqlite3.Row) -> MemberData:
    return MemberData(id=row["id"], name=row["name"], phone=row["phone"])


def tee_time_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> TeeTimeData:
    return TeeTimeData(
        date=row["slot_date"],
        time=hour_and_minute(row["slot_time"]),
        players=tuple(players_for(conn, row["id"])),
    )


def players_for(conn: sqlite3.Connection, tee_time_id: int) -> list[PlayerData]:
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
        PlayerData(
            number=row["player_position"],
            member_id=row["member_id"],
            name=row["name"],
        )
        for row in rows
    ]


def find_or_create_tee_time(conn: sqlite3.Connection, day_text: str, hhmm: str) -> int:
    row = conn.execute(
        """
        SELECT id FROM tee_times
        WHERE slot_date = ? AND substr(slot_time, 1, 5) = ?
        """,
        (day_text, hhmm),
    ).fetchone()
    if row is not None:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO tee_times (slot_date, slot_time) VALUES (?, ?)",
        (day_text, f"{hhmm}:00"),
    )
    return cursor.lastrowid


def reject_closed_seat(players: list[PlayerData], player: PlayerData) -> None:
    if len(players) >= MAX_PLAYERS:
        raise SlotFullError("foursome full")
    if any(existing.member_id == player.member_id for existing in players):
        raise PlayerAlreadyBookedError("already booked on this slot")
    if player.number < 1 or player.number > MAX_PLAYERS:
        raise PositionTakenError(f"player number {player.number} is not open")
    if any(existing.number == player.number for existing in players):
        raise PositionTakenError(f"player number {player.number} is taken")


def insert_booking(conn: sqlite3.Connection, tee_time_id: int, player: PlayerData) -> None:
    conn.execute(
        """
        INSERT INTO bookings (tee_time_id, member_id, player_position)
        VALUES (?, ?, ?)
        """,
        (tee_time_id, player.member_id, player.number),
    )


def hour_and_minute(value: str) -> str:
    """Club times are HH:MM. Stored values may include seconds."""
    return value[:5]


def storage_error(exc: sqlite3.IntegrityError) -> Exception:
    message = str(exc)
    if "members.id" in message:
        return MemberAlreadyExistsError(message)
    if "member_id" in message:
        return PlayerAlreadyBookedError("already booked on this slot")
    if "player_position" in message or "CHECK constraint" in message:
        return PositionTakenError(message)
    return DatabaseUnavailableError("database not reachable")
