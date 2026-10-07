"""ClubStorage against the tee_time_test database.

These tests drop and recreate the tables. They do not use the tee_time database.
"""

from datetime import date

import pymysql
import pytest

from tee_time.app import create_app
from tee_time.store import DatabaseUnavailableError, MemberAlreadyExistsError
from tee_time.tee_time import TeeTimeApp
from tee_time.types import MemberData, PlayerData

DAY = date(2099, 6, 15)
SLOT = "07:00"


def member(member_id, name, phone="555-0100"):
    return MemberData(id=member_id, name=name, phone=phone)


def player(number, member_id, name):
    return PlayerData(number=number, member_id=member_id, name=name)


@pytest.fixture
def club_client(club_storage):
    flask_app = create_app(TeeTimeApp(club_storage))
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def test_create_schema_twice_still_pings_and_lists_no_members_tee_times_or_bookings(
    club_storage,
):
    club_storage.create_schema()
    club_storage.ping()
    assert club_storage.list_members() == []
    assert club_storage.list_tee_times(DAY) == []
    assert club_storage.list_booked() == []
    assert club_storage.get_tee_time(DAY, SLOT) is None
    assert club_storage.get_member("missing") is None


def test_get_member_returns_the_stored_member_and_list_members_returns_both(
    club_storage,
):
    ada = MemberData(id="ada00001", name="Ada Lovelace", phone="555-0100")
    grace = MemberData(id="grace002", name="Grace Hopper", phone="555-0101")
    club_storage.add_member(ada)
    club_storage.add_member(grace)

    assert club_storage.get_member("ada00001") == ada
    stored_ids = {item.id for item in club_storage.list_members()}
    assert stored_ids == {"ada00001", "grace002"}


def test_add_member_raises_member_already_exists_when_that_id_is_taken(club_storage):
    ada = member("ada00001", "Ada Lovelace")
    club_storage.add_member(ada)
    with pytest.raises(MemberAlreadyExistsError, match="already exists"):
        club_storage.add_member(ada)


def test_first_booking_creates_the_tee_time_and_a_later_player_joins_in_number_order(
    club_storage,
):
    club_storage.add_member(member("ada00001", "Ada Lovelace"))
    club_storage.add_member(member("grace002", "Grace Hopper", "555-0101"))

    created = club_storage.add_player(
        DAY, "07:00:00", player(2, "ada00001", "Ada Lovelace")
    )
    assert created.date == "2099-06-15"
    assert created.time == "07:00"
    assert [booked.number for booked in created.players] == [2]

    updated = club_storage.add_player(DAY, SLOT, player(1, "grace002", "Grace Hopper"))
    assert [booked.number for booked in updated.players] == [1, 2]
    assert club_storage.get_tee_time(DAY, SLOT).players == updated.players


def test_list_tee_times_returns_the_booked_slot_and_nothing_on_another_day(
    club_storage,
):
    club_storage.add_member(member("ada00001", "Ada Lovelace"))
    added = club_storage.add_player(DAY, SLOT, player(1, "ada00001", "Ada Lovelace"))
    assert club_storage.list_tee_times(DAY) == [added]
    assert club_storage.list_tee_times(date(2099, 6, 16)) == []


def test_list_booked_returns_a_slot_only_after_a_player_is_added(club_storage):
    club_storage.add_member(member("ada00001", "Ada Lovelace"))
    assert club_storage.list_booked() == []
    added = club_storage.add_player(DAY, SLOT, player(1, "ada00001", "Ada Lovelace"))
    assert club_storage.list_booked() == [added]


def _store_players(club_storage, count):
    for index in range(1, count + 1):
        club_storage.add_member(member(f"m{index}", f"Player {index}"))


def test_add_player_rejects_a_duplicate_member_and_keeps_the_original_player(
    club_storage,
):
    _store_players(club_storage, 2)
    club_storage.add_player(DAY, "08:00", player(1, "m1", "Player 1"))
    with pytest.raises(DatabaseUnavailableError):
        club_storage.add_player(DAY, "08:00", player(2, "m1", "Player 1"))
    assert len(club_storage.get_tee_time(DAY, "08:00").players) == 1


def test_add_player_rejects_a_taken_player_number_and_keeps_the_original_player(
    club_storage,
):
    _store_players(club_storage, 2)
    club_storage.add_player(DAY, "08:00", player(1, "m1", "Player 1"))
    with pytest.raises(DatabaseUnavailableError):
        club_storage.add_player(DAY, "08:00", player(1, "m2", "Player 2"))
    assert len(club_storage.get_tee_time(DAY, "08:00").players) == 1


def test_add_player_rejects_a_player_number_outside_1_to_4(club_storage):
    _store_players(club_storage, 2)
    club_storage.add_player(DAY, "08:00", player(1, "m1", "Player 1"))
    with pytest.raises(DatabaseUnavailableError):
        club_storage.add_player(DAY, "08:00", player(0, "m2", "Player 2"))
    assert len(club_storage.get_tee_time(DAY, "08:00").players) == 1


def test_add_player_rejects_a_fifth_player_and_keeps_the_foursome(club_storage):
    _store_players(club_storage, 5)
    for index in range(1, 5):
        club_storage.add_player(
            DAY, SLOT, player(index, f"m{index}", f"Player {index}")
        )
    with pytest.raises(DatabaseUnavailableError):
        club_storage.add_player(DAY, SLOT, player(1, "m5", "Player 5"))
    assert len(club_storage.get_tee_time(DAY, SLOT).players) == 4


def test_unknown_member_booking_raises_database_unavailable_and_stores_nothing(
    club_storage,
):
    with pytest.raises(DatabaseUnavailableError):
        club_storage.add_player(DAY, SLOT, player(1, "missing", "Nobody"))
    assert club_storage.get_tee_time(DAY, SLOT) is None


def test_player_number_9_stores_no_tee_time(club_storage):
    club_storage.add_member(member("m2", "Grace", "555-0101"))
    with pytest.raises(DatabaseUnavailableError):
        club_storage.add_player(DAY, "08:00", player(9, "m2", "Grace"))
    assert club_storage.get_tee_time(DAY, "08:00") is None


def test_add_player_rolls_back_the_tee_time_when_mysql_disconnects_during_insert(
    club_storage, monkeypatch
):
    club_storage.add_member(member("m1", "Ada"))

    def fail(*args, **kwargs):
        raise pymysql.OperationalError(2006, "MySQL server has gone away")

    monkeypatch.setattr("tee_time.db.insert_booking", fail)
    with pytest.raises(DatabaseUnavailableError):
        club_storage.add_player(DAY, SLOT, player(1, "m1", "Ada"))
    assert club_storage.get_tee_time(DAY, SLOT) is None


def test_add_player_raises_database_unavailable_when_the_saved_slot_cannot_be_reread(
    club_storage, monkeypatch
):
    club_storage.add_member(member("m1", "Ada"))
    monkeypatch.setattr(club_storage, "get_tee_time", lambda day, slot_time: None)
    with pytest.raises(DatabaseUnavailableError):
        club_storage.add_player(DAY, SLOT, player(1, "m1", "Ada"))


def test_ping_raises_database_unavailable_when_the_members_table_is_missing(
    club_storage,
):
    conn = club_storage._connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS bookings")
            cursor.execute("DROP TABLE IF EXISTS tee_times")
            cursor.execute("DROP TABLE IF EXISTS members")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(DatabaseUnavailableError, match="members table missing"):
        club_storage.ping()


_JSON = {"Accept": "application/json"}
_SLOT_URL = "/tee-times/2099-06-15T07:00:00"


def _add_ada(client):
    response = client.post(
        "/members", json={"name": "Ada Lovelace", "phone": "555-0100"}
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def test_get_health_returns_200_ok_when_the_members_table_exists(club_client):
    response = club_client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_get_members_json_returns_an_empty_list_when_nobody_is_stored(club_client):
    response = club_client.get("/members", headers=_JSON)
    assert response.status_code == 200
    assert response.get_json() == {"members": []}


def test_post_members_without_a_phone_returns_400(club_client):
    response = club_client.post("/members", json={"name": "Ada"})
    assert response.status_code == 400


def test_post_members_with_a_blank_name_returns_400_name_must_not_be_blank(
    club_client,
):
    response = club_client.post("/members", json={"name": "  ", "phone": "555-0100"})
    assert response.status_code == 400
    assert response.get_json()["error"]["message"] == "name must not be blank"


def test_post_members_returns_201_and_get_members_lists_that_name_and_phone(
    club_client,
):
    member_id = _add_ada(club_client)
    roster = club_client.get("/members", headers=_JSON)
    assert roster.get_json()["members"] == [
        {"id": member_id, "name": "Ada Lovelace", "phone": "555-0100"}
    ]


def test_get_tee_times_without_a_date_returns_400(club_client):
    response = club_client.get("/tee-times")
    assert response.status_code == 400


def test_get_tee_times_returns_sixteen_slots_and_0700_is_empty_and_bookable(
    club_client,
):
    response = club_client.get("/tee-times?date=2099-06-15")
    assert response.status_code == 200
    slots = response.get_json()["teeTimes"]
    assert len(slots) == 16
    seven = next(slot for slot in slots if slot["time"] == "07:00")
    assert seven["playerCount"] == 0
    assert seven["bookable"] is True


def test_get_tee_time_at_1900_returns_404_because_it_is_not_a_default_time(club_client):
    response = club_client.get("/tee-times/2099-06-15T19:00:00")
    assert response.status_code == 404


def test_post_booking_with_a_slot_id_that_is_not_a_slot_returns_400(club_client):
    member_id = _add_ada(club_client)
    response = club_client.post(
        "/tee-times/not-a-slot/bookings", json={"memberId": member_id}
    )
    assert response.status_code == 400


def test_post_booking_for_a_member_id_that_is_not_stored_returns_404(club_client):
    response = club_client.post(f"{_SLOT_URL}/bookings", json={"memberId": "missing"})
    assert response.status_code == 404


def test_post_booking_returns_201_and_that_member_is_no_longer_available(club_client):
    member_id = _add_ada(club_client)
    response = club_client.post(f"{_SLOT_URL}/bookings", json={"memberId": member_id})
    assert response.status_code == 201
    body = response.get_json()
    assert body["playerCount"] == 1
    assert body["players"][0]["memberId"] == member_id
    assert body["availableMembers"] == []


def test_post_booking_again_for_the_same_member_returns_400_already_booked(club_client):
    member_id = _add_ada(club_client)
    first = club_client.post(f"{_SLOT_URL}/bookings", json={"memberId": member_id})
    assert first.status_code == 201
    again = club_client.post(f"{_SLOT_URL}/bookings", json={"memberId": member_id})
    assert again.status_code == 400
    assert again.get_json()["error"]["message"] == "already booked on this slot"


def test_get_reserved_json_lists_a_future_booking_as_upcoming_and_past_is_empty(
    club_client,
):
    member_id = _add_ada(club_client)
    booked = club_client.post(f"{_SLOT_URL}/bookings", json={"memberId": member_id})
    assert booked.status_code == 201
    response = club_client.get("/reserved", headers=_JSON)
    assert response.status_code == 200
    upcoming = [slot["id"] for slot in response.get_json()["upcoming"]]
    assert upcoming == ["2099-06-15T07:00:00"]
    assert response.get_json()["past"] == []


def test_get_health_returns_503_unavailable_when_the_members_table_is_missing(
    club_client, club_storage
):
    conn = club_storage._connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS bookings")
            cursor.execute("DROP TABLE IF EXISTS tee_times")
            cursor.execute("DROP TABLE IF EXISTS members")
        conn.commit()
    finally:
        conn.close()
    response = club_client.get("/health")
    assert response.status_code == 503
    assert response.get_json() == {"status": "unavailable"}
