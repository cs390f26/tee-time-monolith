"""MySQL storage for members and tee times.

Maps rows to MemberData and TeeTimeData. PyMySQL errors become storage
exceptions so the application layer does not import pymysql.
"""

from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import pymysql
import pymysql.cursors

from tee_time.store import DatabaseUnavailableError, MemberAlreadyExistsError
from tee_time.types import MemberData, PlayerData, TeeTimeData

_SCHEMA = Path(__file__).resolve().parents[2] / "scripts" / "schema.sql"
_CONNECT_TIMEOUT = 5


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
        return self._load_tee_times(
            """
            SELECT id, slot_date, slot_time
            FROM tee_times
            WHERE slot_date = %s
            ORDER BY slot_time
            """,
            (day.isoformat(),),
        )

    def list_booked(self) -> list[TeeTimeData]:
        slots = self._load_tee_times(
            """
            SELECT id, slot_date, slot_time
            FROM tee_times
            ORDER BY slot_date, slot_time
            """,
            (),
        )
        return [slot for slot in slots if slot.players]

    def get_tee_time(self, day: date, slot_time: str) -> TeeTimeData | None:
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

    def add_player(self, day: date, slot_time: str, player: PlayerData) -> TeeTimeData:
        day_text = day.isoformat()
        hhmm = hour_and_minute(slot_time)
        try:
            with self._session() as conn:
                tee_time_id = find_or_create_tee_time(conn, day_text, hhmm)
                insert_booking(conn, tee_time_id, player)
        except pymysql.Error as exc:
            raise DatabaseUnavailableError("database not reachable") from exc
        updated = self.get_tee_time(day, hhmm)
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


def players_for(conn: pymysql.connections.Connection, tee_time_id: int) -> list[PlayerData]:
    rows = fetchall(
        conn,
        """
        SELECT b.player_position, b.member_id, m.name
        FROM bookings b
        JOIN members m ON m.id = b.member_id
        WHERE b.tee_time_id = %s
        ORDER BY b.player_position
        """,
        (tee_time_id,),
    )
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
    row = fetchone(
        conn,
        """
        SELECT id FROM tee_times
        WHERE slot_date = %s AND LEFT(slot_time, 5) = %s
        """,
        (day_text, hhmm),
    )
    if row is not None:
        return row["id"]
    return execute(
        conn,
        "INSERT INTO tee_times (slot_date, slot_time) VALUES (%s, %s)",
        (day_text, f"{hhmm}:00"),
    )


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


def as_date_text(value: date) -> str:
    """DATE columns come back as date objects. The app uses YYYY-MM-DD text."""
    return value.isoformat()


def as_hhmm(value: timedelta) -> str:
    """TIME columns come back as timedeltas. The app uses HH:MM text."""
    total = int(value.total_seconds())
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return f"{hours:02d}:{minutes:02d}"


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
