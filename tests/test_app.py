import runpy
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tee_time.app import (
    RequestError,
    create_app,
    launch,
    parse_day,
    parse_member_id,
    parse_new_member,
    parse_slot_id,
)
from tee_time.db import DatabaseUnavailableError
from tee_time.tee_time import NotFoundError, ServiceUnavailableError, ValidationError
from tee_time.types import MemberView, PlayerData, TeeTimeSlot, TeeTimeView


@pytest.fixture
def mock_tee_time_app():
    return MagicMock()


@pytest.fixture
def client(mock_tee_time_app):
    flask_app = create_app(mock_tee_time_app)
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


# --- Unit Tests for Helper Parser Functions ---

def test_parse_day_valid():
    assert parse_day("2026-09-19") == date(2026, 9, 19)


@pytest.mark.parametrize("raw", [None, "", "   ", "invalid-date", "2026-13-01", "2026-09-32", "2026-9-1"])
def test_parse_day_invalid(raw):
    with pytest.raises(RequestError):
        parse_day(raw)


def test_parse_slot_id_valid():
    day, hour_min = parse_slot_id("2026-09-19T07:00:00")
    assert day == date(2026, 9, 19)
    assert hour_min == "07:00"


@pytest.mark.parametrize("slot_id", [
    "2026-09-19 07:00:00",
    "2026-09-19T07:00",
    "2026-09-19T07:00:01",
    "invalidT07:00:00",
    "2026-09-19T99:99:00",
    "2026-13-01T07:00:00",
])
def test_parse_slot_id_invalid(slot_id):
    with pytest.raises(RequestError, match="tee time id must look like"):
        parse_slot_id(slot_id)


def test_parse_new_member_valid(client):
    with client.application.test_request_context("/", json={"name": "Alice", "phone": "555-0100"}):
        name, phone = parse_new_member()
        assert name == "Alice"
        assert phone == "555-0100"


@pytest.mark.parametrize("payload", [
    None,
    "not json",
    {"name": "Alice"},
    {"phone": "555-0100"},
    {"name": 123, "phone": "555-0100"},
])
def test_parse_new_member_invalid(client, payload):
    with client.application.test_request_context("/", json=payload if isinstance(payload, dict) else None, data=payload if isinstance(payload, str) else None):
        with pytest.raises(RequestError):
            parse_new_member()


def test_parse_member_id_valid(client):
    with client.application.test_request_context("/", json={"memberId": " m101 "}):
        assert parse_member_id() == "m101"


@pytest.mark.parametrize("payload", [
    None,
    {},
    {"memberId": ""},
    {"memberId": "   "},
    {"memberId": 123},
])
def test_parse_member_id_invalid(client, payload):
    with client.application.test_request_context("/", json=payload if isinstance(payload, dict) else None):
        with pytest.raises(RequestError):
            parse_member_id()


# --- Template Route Tests ---

def test_static_html_pages(client):
    res_times = client.get("/")
    assert res_times.status_code == 200

    res_book = client.get("/book")
    assert res_book.status_code == 200


def test_reserved_page_html(client):
    res = client.get("/reserved", headers={"Accept": "text/html"})
    assert res.status_code == 200


def test_members_page_html(client):
    res = client.get("/members", headers={"Accept": "text/html"})
    assert res.status_code == 200


# --- Health Endpoint ---

def test_health_success(client, mock_tee_time_app):
    mock_tee_time_app.health.return_value = None
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


def test_health_unavailable(client, mock_tee_time_app):
    mock_tee_time_app.health.side_effect = ServiceUnavailableError("DB down")
    res = client.get("/health")
    assert res.status_code == 503
    assert res.get_json() == {"status": "unavailable"}


# --- Members API Endpoints ---

def test_get_members_json_success(client, mock_tee_time_app):
    member = MemberView(id="m1", name="Alice", phone="555-0100")
    mock_tee_time_app.list_members.return_value = [member]

    res = client.get("/members", headers={"Accept": "application/json"})
    assert res.status_code == 200
    assert res.get_json() == {
        "members": [{"id": "m1", "name": "Alice", "phone": "555-0100"}]
    }


def test_get_members_json_unavailable(client, mock_tee_time_app):
    mock_tee_time_app.list_members.side_effect = ServiceUnavailableError()
    res = client.get("/members", headers={"Accept": "application/json"})
    assert res.status_code == 503


def test_add_member_success(client, mock_tee_time_app):
    mock_tee_time_app.add_member.return_value = "m102"
    res = client.post("/members", json={"name": "Bob", "phone": "555-0200"})
    assert res.status_code == 201
    assert res.get_json() == {"id": "m102"}


def test_add_member_validation_error(client, mock_tee_time_app):
    mock_tee_time_app.add_member.side_effect = ValidationError("name required")
    res = client.post("/members", json={"name": "", "phone": "555-0200"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "BAD_REQUEST"


def test_add_member_unavailable(client, mock_tee_time_app):
    mock_tee_time_app.add_member.side_effect = ServiceUnavailableError()
    res = client.post("/members", json={"name": "Bob", "phone": "555-0200"})
    assert res.status_code == 503


# --- Reserved API Endpoints ---

def test_reserved_json_success(client, mock_tee_time_app):
    slot = TeeTimeSlot(
        id="2026-09-19T07:00:00",
        date="2026-09-19",
        time="07:00",
        player_names=("Alice",),
        player_count=1,
        bookable=True,
    )
    mock_tee_time_app.list_reserved.return_value = ([slot], [])

    res = client.get("/reserved", headers={"Accept": "application/json"})
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["upcoming"]) == 1
    assert len(data["past"]) == 0


def test_reserved_json_unavailable(client, mock_tee_time_app):
    mock_tee_time_app.list_reserved.side_effect = ServiceUnavailableError()
    res = client.get("/reserved", headers={"Accept": "application/json"})
    assert res.status_code == 503


# --- Tee Times API Endpoints ---

def test_list_tee_times_success(client, mock_tee_time_app):
    slot = TeeTimeSlot(
        id="2026-09-19T07:00:00",
        date="2026-09-19",
        time="07:00",
        player_names=(),
        player_count=0,
        bookable=True,
    )
    mock_tee_time_app.list_tee_times.return_value = [slot]

    res = client.get("/tee-times?date=2026-09-19")
    assert res.status_code == 200
    assert len(res.get_json()["teeTimes"]) == 1


def test_list_tee_times_bad_request(client):
    res = client.get("/tee-times?date=invalid-date")
    assert res.status_code == 400


def test_list_tee_times_unavailable(client, mock_tee_time_app):
    mock_tee_time_app.list_tee_times.side_effect = ServiceUnavailableError()
    res = client.get("/tee-times?date=2026-09-19")
    assert res.status_code == 503


def test_get_tee_time_success(client, mock_tee_time_app):
    player = PlayerData(number=1, member_id="m1", name="Alice")
    member = MemberView(id="m2", name="Bob", phone="555-0200")
    view = TeeTimeView(
        id="2026-09-19T07:00:00",
        date="2026-09-19",
        time="07:00",
        players=(player,),
        player_count=1,
        bookable=True,
        available_members=(member,),
    )
    mock_tee_time_app.get_tee_time.return_value = view

    res = client.get("/tee-times/2026-09-19T07:00:00")
    assert res.status_code == 200
    data = res.get_json()
    assert data["id"] == "2026-09-19T07:00:00"
    assert len(data["players"]) == 1
    assert len(data["availableMembers"]) == 1


def test_get_tee_time_not_found(client, mock_tee_time_app):
    mock_tee_time_app.get_tee_time.side_effect = NotFoundError("slot not found")
    res = client.get("/tee-times/2026-09-19T07:00:00")
    assert res.status_code == 404


def test_get_tee_time_unavailable(client, mock_tee_time_app):
    mock_tee_time_app.get_tee_time.side_effect = ServiceUnavailableError()
    res = client.get("/tee-times/2026-09-19T07:00:00")
    assert res.status_code == 503


def test_add_booking_success(client, mock_tee_time_app):
    view = TeeTimeView(
        id="2026-09-19T07:00:00",
        date="2026-09-19",
        time="07:00",
        players=(),
        player_count=1,
        bookable=True,
        available_members=(),
    )
    mock_tee_time_app.book.return_value = view

    res = client.post("/tee-times/2026-09-19T07:00:00/bookings", json={"memberId": "m1"})
    assert res.status_code == 201


def test_add_booking_validation_error(client, mock_tee_time_app):
    mock_tee_time_app.book.side_effect = ValidationError("foursome full")
    res = client.post("/tee-times/2026-09-19T07:00:00/bookings", json={"memberId": "m1"})
    assert res.status_code == 400


def test_add_booking_not_found_error(client, mock_tee_time_app):
    mock_tee_time_app.book.side_effect = NotFoundError("member not found")
    res = client.post("/tee-times/2026-09-19T07:00:00/bookings", json={"memberId": "m1"})
    assert res.status_code == 404


def test_add_booking_unavailable(client, mock_tee_time_app):
    mock_tee_time_app.book.side_effect = ServiceUnavailableError()
    res = client.post("/tee-times/2026-09-19T07:00:00/bookings", json={"memberId": "m1"})
    assert res.status_code == 503


_SETTINGS = {
    "MYSQL_HOST": "127.0.0.1",
    "MYSQL_PORT": "3306",
    "MYSQL_USER": "tee_time",
    "MYSQL_PASSWORD": "tee_time",
    "MYSQL_DATABASE": "tee_time_test",
}


def test_launch_creates_the_schema_pings_mysql_and_returns_the_flask_app(monkeypatch):
    storage = MagicMock()
    flask_app = MagicMock()
    monkeypatch.setattr("tee_time.app.ensure_settings", lambda: _SETTINGS)
    monkeypatch.setattr("tee_time.app.ClubStorage", MagicMock(return_value=storage))
    monkeypatch.setattr("tee_time.app.create_app", lambda app_logic: flask_app)

    assert launch() is flask_app
    storage.create_schema.assert_called_once()
    storage.ping.assert_called_once()


def test_launch_raises_runtime_error_when_create_schema_cannot_reach_mysql(monkeypatch):
    storage = MagicMock()
    storage.create_schema.side_effect = DatabaseUnavailableError("down")
    monkeypatch.setattr("tee_time.app.ensure_settings", lambda: _SETTINGS)
    monkeypatch.setattr("tee_time.app.ClubStorage", MagicMock(return_value=storage))

    with pytest.raises(RuntimeError, match="Database not reachable"):
        launch()


def test_running_app_as_main_starts_flask_in_debug_mode_on_port_5000(monkeypatch):
    storage = MagicMock()
    started = {}

    def fake_run(self, debug=False, port=None, **kwargs):
        started["debug"] = debug
        started["port"] = port

    monkeypatch.setattr("tee_time.settings.ensure_settings", lambda: _SETTINGS)
    monkeypatch.setattr("tee_time.db.ClubStorage", MagicMock(return_value=storage))
    monkeypatch.setattr("flask.Flask.run", fake_run)
    _run_app_as_main()
    storage.create_schema.assert_called_once()
    storage.ping.assert_called_once()
    assert started == {"debug": True, "port": 5000}


def test_running_app_as_main_exits_1_and_prints_the_error_when_mysql_is_down(
    monkeypatch, capsys
):
    storage = MagicMock()
    storage.ping.side_effect = DatabaseUnavailableError("down")
    monkeypatch.setattr("tee_time.settings.ensure_settings", lambda: _SETTINGS)
    monkeypatch.setattr("tee_time.db.ClubStorage", MagicMock(return_value=storage))

    with pytest.raises(SystemExit) as caught:
        _run_app_as_main()
    assert caught.value.code == 1
    assert "Database not reachable" in capsys.readouterr().err


def _run_app_as_main():
    previous = sys.modules.get("__main__")
    app_path = Path(__file__).resolve().parents[1] / "src" / "tee_time" / "app.py"
    try:
        runpy.run_path(str(app_path), run_name="__main__")
    finally:
        if previous is not None:
            sys.modules["__main__"] = previous