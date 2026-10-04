"""MySQL storage for members and tee times.

Maps rows to MemberData and TeeTimeData. PyMySQL errors become storage
exceptions so the application layer does not import pymysql.
"""

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pymysql
import pymysql.cursors

from tee_time.store import (
    DatabaseUnavailableError,
    MemberAlreadyExistsError,
    PlayerAlreadyBookedError,
    PositionTakenError,
    SlotFullError,
)
from tee_time.types import MAX_PLAYERS, MemberData, PlayerData, TeeTimeData

_SCHEMA = Path(__file__).resolve().parents[2] / "scripts" / "schema.sql"
_CONNECT_TIMEOUT = 5
_DUPLICATE_KEY = 1062
_CHECK_VIOLATION = {3819, 4025}


class ClubStorage:
    """ClubStore backed by a MySQL database."""

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        database: str,
        port: int = 3306,
    ):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database

    def create_schema(self) -> None:
        """Create members, tee times, and bookings if they are not there yet."""
        try:
            with self._session() as conn, conn.cursor() as cursor:
                for statement in create_table_statements():
                    cursor.execute(statement)
        except pymysql.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc

    def ping(self) -> None:
        """Raise DatabaseUnavailableError when the server or members table is missing."""
        try:
            with self._session() as conn:
                row = fetchone(
                    conn,
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE() AND table_name = 'members'
                    """,
                    (),
                )
        except pymysql.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc
        if row is None:
            raise DatabaseUnavailableError("members table missing")

    def list_members(self) -> list[MemberData]:
        try:
            with self._session() as conn:
                rows = fetchall(conn, "SELECT id, name, phone FROM members", ())
        except pymysql.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc
        return [member_from_row(row) for row in rows]

    def get_member(self, member_id: str) -> MemberData | None:
        try:
            with self._session() as conn:
                row = fetchone(
                    conn,
                    "SELECT id, name, phone FROM members WHERE id = %s",
                    (member_id,),
                )
        except pymysql.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc
        if row is None:
            return None
        return member_from_row(row)

    def add_member(self, member: MemberData) -> None:
        try:
            with self._session() as conn:
                execute(
                    conn,
                    "INSERT INTO members (id, name, phone) VALUES (%s, %s, %s)",
                    (member.id, member.name, member.phone),
                )
        except pymysql.IntegrityError as exc:
            raise MemberAlreadyExistsError(f"member {member.id} already exists") from exc
        except pymysql.Error as exc:
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
            WHERE slot_date = %s
            ORDER BY slot_time
            """,
            (day.isoformat(),),
        )

    def slot_at(self, day: date, slot_time: str) -> TeeTimeData | None:
        slots = self._load_tee_times(
            """
            SELECT id, slot_date, slot_time
            FROM tee_times
            WHERE slot_date = %s AND LEFT(slot_time, 5) = %s
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
            conn.begin()
            tee_time_id = find_or_create_tee_time(conn, day_text, hhmm)
            reject_closed_seat(players_for(conn, tee_time_id, lock=True), player)
            insert_booking(conn, tee_time_id, player)
            conn.commit()
        except (SlotFullError, PlayerAlreadyBookedError, PositionTakenError):
            conn.rollback()
            raise
        except pymysql.IntegrityError as exc:
            conn.rollback()
            raise storage_error(exc) from exc
        except pymysql.Error as exc:
            conn.rollback()
            if is_check_violation(exc):
                raise PositionTakenError(str(exc)) from exc
            raise DatabaseUnavailableError("database not reachable") from exc
        finally:
            conn.close()
        updated = self.slot_at(day, hhmm)
        if updated is None:
            raise DatabaseUnavailableError("database not reachable")
        return updated

    def _load_tee_times(self, sql: str, params: tuple) -> list[TeeTimeData]:
        try:
            with self._session() as conn:
                rows = fetchall(conn, sql, params)
                return [tee_time_from_row(conn, row) for row in rows]
        except pymysql.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc

    def _connect(self) -> pymysql.connections.Connection:
        try:
            return pymysql.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=_CONNECT_TIMEOUT,
            )
        except pymysql.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc

    @contextmanager
    def _session(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


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


def member_from_row(row: dict) -> MemberData:
    return MemberData(id=row["id"], name=row["name"], phone=row["phone"])


def tee_time_from_row(conn: pymysql.connections.Connection, row: dict) -> TeeTimeData:
    return TeeTimeData(
        date=as_date_text(row["slot_date"]),
        time=as_hhmm(row["slot_time"]),
        players=tuple(players_for(conn, row["id"])),
    )


def players_for(
    conn: pymysql.connections.Connection,
    tee_time_id: int,
    lock: bool = False,
) -> list[PlayerData]:
    sql = """
        SELECT b.player_position, b.member_id, m.name
        FROM bookings b
        JOIN members m ON m.id = b.member_id
        WHERE b.tee_time_id = %s
        ORDER BY b.player_position
    """
    if lock:
        sql += " FOR UPDATE"
    rows = fetchall(conn, sql, (tee_time_id,))
    return [
        PlayerData(
            number=row["player_position"],
            member_id=row["member_id"],
            name=row["name"],
        )
        for row in rows
    ]


def find_or_create_tee_time(
    conn: pymysql.connections.Connection, day_text: str, hhmm: str
) -> int:
    row = locked_tee_time(conn, day_text, hhmm)
    if row is not None:
        return row["id"]
    try:
        return execute(
            conn,
            "INSERT INTO tee_times (slot_date, slot_time) VALUES (%s, %s)",
            (day_text, f"{hhmm}:00"),
        )
    except pymysql.IntegrityError as exc:
        if "uq_slot" not in str(exc):
            raise
        row = locked_tee_time(conn, day_text, hhmm)
        if row is None:
            raise
        return row["id"]


def locked_tee_time(conn: pymysql.connections.Connection, day_text: str, hhmm: str):
    return fetchone(
        conn,
        """
        SELECT id FROM tee_times
        WHERE slot_date = %s AND LEFT(slot_time, 5) = %s
        FOR UPDATE
        """,
        (day_text, hhmm),
    )


def reject_closed_seat(players: list[PlayerData], player: PlayerData) -> None:
    if len(players) >= MAX_PLAYERS:
        raise SlotFullError("foursome full")
    if any(existing.member_id == player.member_id for existing in players):
        raise PlayerAlreadyBookedError("already booked on this slot")
    if player.number < 1 or player.number > MAX_PLAYERS:
        raise PositionTakenError(f"player number {player.number} is not open")
    if any(existing.number == player.number for existing in players):
        raise PositionTakenError(f"player number {player.number} is taken")


def insert_booking(
    conn: pymysql.connections.Connection, tee_time_id: int, player: PlayerData
) -> None:
    execute(
        conn,
        """
        INSERT INTO bookings (tee_time_id, member_id, player_position)
        VALUES (%s, %s, %s)
        """,
        (tee_time_id, player.member_id, player.number),
    )


def hour_and_minute(value: str) -> str:
    """Club times are HH:MM. Stored values may include seconds."""
    return value[:5]


def as_date_text(value) -> str:
    """DATE columns come back as date objects. The app uses YYYY-MM-DD text."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def as_hhmm(value) -> str:
    """TIME columns come back as timedeltas. The app uses HH:MM text."""
    if isinstance(value, timedelta):
        total = int(value.total_seconds())
        hours, rem = divmod(total, 3600)
        minutes = rem // 60
        return f"{hours:02d}:{minutes:02d}"
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)[:5]


def storage_error(exc: pymysql.IntegrityError) -> Exception:
    code = exc.args[0] if exc.args else None
    message = str(exc)
    if code in _CHECK_VIOLATION or "chk_player_position" in message:
        return PositionTakenError(message)
    if code == _DUPLICATE_KEY:
        if "uq_booking_member" in message:
            return PlayerAlreadyBookedError("already booked on this slot")
        if "uq_booking_position" in message:
            return PositionTakenError(message)
        if "PRIMARY" in message:
            return MemberAlreadyExistsError(message)
    return DatabaseUnavailableError("database not reachable")


def is_check_violation(exc: pymysql.Error) -> bool:
    code = exc.args[0] if exc.args else None
    return code in _CHECK_VIOLATION or "chk_player_position" in str(exc)


def fetchall(conn: pymysql.connections.Connection, sql: str, params: tuple) -> list:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def fetchone(conn: pymysql.connections.Connection, sql: str, params: tuple):
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def execute(conn: pymysql.connections.Connection, sql: str, params: tuple) -> int:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.lastrowid
