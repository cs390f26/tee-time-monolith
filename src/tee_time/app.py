"""JSON routes for tee times and members.

Handlers check the request, call TeeTimeApp, and return JSON or HTML.
"""

import sys
from datetime import date, time

from flask import Flask, jsonify, render_template, request

from tee_time.db import ClubStorage, DatabaseUnavailableError
from tee_time.settings import ensure_settings
from tee_time.tee_time import (
    NotFoundError,
    ServiceUnavailableError,
    TeeTimeApp,
    ValidationError,
)
from tee_time.types import MemberView, TeeTimeSlot, TeeTimeView

_SLOT_ID_MESSAGE = "tee time id must look like 2026-09-19T07:00:00"


class RequestError(Exception):
    """Raised when the request cannot be read. The application was not called."""


def _error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def _unavailable():
    return jsonify({"status": "unavailable"}), 503


def _wants_json() -> bool:
    """True when the client asked for JSON rather than the HTML page."""
    return (
        request.accept_mimetypes.best_match(["text/html", "application/json"])
        == "application/json"
    )


def parse_day(raw: str | None) -> date:
    """Return a YYYY-MM-DD date, or raise RequestError."""
    if raw is None or not raw.strip():
        raise RequestError("date query parameter is required")
    text = raw.strip()
    if not _iso_day(text):
        raise RequestError("date must be YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise RequestError("date must be YYYY-MM-DD") from None


def parse_slot_id(slot_id: str) -> tuple[date, str]:
    """Return (date, HH:MM) for an id like 2026-09-19T07:00:00."""
    date_text, separator, clock_text = slot_id.partition("T")
    hour_minute = clock_text[:-3]
    if separator != "T" or not clock_text.endswith(":00"):
        raise RequestError(_SLOT_ID_MESSAGE)
    if not _iso_day(date_text) or not _iso_hhmm(hour_minute):
        raise RequestError(_SLOT_ID_MESSAGE)
    try:
        parsed_day = date.fromisoformat(date_text)
        time.fromisoformat(hour_minute)
    except ValueError:
        raise RequestError(_SLOT_ID_MESSAGE) from None
    return parsed_day, hour_minute


def parse_new_member() -> tuple[str, str]:
    """Return name and phone from the JSON body, or raise RequestError."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise RequestError("JSON body required")
    name = body.get("name")
    phone = body.get("phone")
    if not isinstance(name, str) or not isinstance(phone, str):
        raise RequestError("name and phone are required")
    return name, phone


def parse_member_id() -> str:
    """Return memberId from the JSON body, or raise RequestError."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("memberId"), str):
        raise RequestError("memberId is required")
    member_id = body["memberId"].strip()
    if not member_id:
        raise RequestError("memberId must not be blank")
    return member_id


def _iso_day(text: str) -> bool:
    parts = text.split("-")
    return (
        len(parts) == 3
        and len(parts[0]) == 4
        and len(parts[1]) == 2
        and len(parts[2]) == 2
        and all(part.isdigit() for part in parts)
    )


def _iso_hhmm(text: str) -> bool:
    parts = text.split(":")
    return (
        len(parts) == 2
        and len(parts[0]) == 2
        and len(parts[1]) == 2
        and all(part.isdigit() for part in parts)
    )


def _member_json(member: MemberView) -> dict:
    return {"id": member.id, "name": member.name, "phone": member.phone}


def _summary_json(slot: TeeTimeSlot) -> dict:
    return {
        "id": slot.id,
        "date": slot.date,
        "time": slot.time,
        "playerNames": list(slot.player_names),
        "playerCount": slot.player_count,
        "bookable": slot.bookable,
    }


def _tee_time_json(slot: TeeTimeView) -> dict:
    return {
        "id": slot.id,
        "date": slot.date,
        "time": slot.time,
        "players": [
            {"number": player.number, "memberId": player.member_id, "name": player.name}
            for player in slot.players
        ],
        "playerCount": slot.player_count,
        "bookable": slot.bookable,
        "availableMembers": [_member_json(member) for member in slot.available_members],
    }


def create_app(tee_time_app: TeeTimeApp) -> Flask:
    """Build the Flask app and add routes."""
    app = Flask(__name__)

    @app.errorhandler(RequestError)
    def bad_request(exc: RequestError):
        return _error("BAD_REQUEST", str(exc), 400)

    @app.get("/")
    def times_page():
        return render_template("times.html")

    @app.get("/book")
    def book_page():
        return render_template("book.html")

    @app.get("/reserved")
    def reserved_page():
        if _wants_json():
            try:
                upcoming, past = tee_time_app.list_reserved()
            except ServiceUnavailableError:
                return _unavailable()
            return jsonify(
                {
                    "upcoming": [_summary_json(slot) for slot in upcoming],
                    "past": [_summary_json(slot) for slot in past],
                }
            ), 200
        return render_template("reserved.html")

    @app.get("/members")
    def members_page():
        if _wants_json():
            try:
                members = tee_time_app.list_members()
            except ServiceUnavailableError:
                return _unavailable()
            return jsonify({"members": [_member_json(member) for member in members]}), 200
        return render_template("members.html")

    @app.get("/health")
    def health():
        try:
            tee_time_app.health()
        except ServiceUnavailableError:
            return _unavailable()
        return jsonify({"status": "ok"}), 200

    @app.get("/tee-times")
    def list_tee_times():
        day = parse_day(request.args.get("date"))
        try:
            slots = tee_time_app.list_tee_times(day)
        except ServiceUnavailableError:
            return _unavailable()
        return jsonify({"teeTimes": [_summary_json(slot) for slot in slots]}), 200

    @app.get("/tee-times/<slot_id>")
    def get_tee_time(slot_id):
        day, slot_time = parse_slot_id(slot_id)
        try:
            slot = tee_time_app.get_tee_time(day, slot_time)
        except NotFoundError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        except ServiceUnavailableError:
            return _unavailable()
        return jsonify(_tee_time_json(slot)), 200

    @app.post("/members")
    def add_member():
        name, phone = parse_new_member()
        try:
            member_id = tee_time_app.add_member(name, phone)
        except ValidationError as exc:
            return _error("BAD_REQUEST", str(exc), 400)
        except ServiceUnavailableError:
            return _unavailable()
        return jsonify({"id": member_id}), 201

    @app.post("/tee-times/<slot_id>/bookings")
    def add_booking(slot_id):
        day, slot_time = parse_slot_id(slot_id)
        member_id = parse_member_id()
        try:
            slot = tee_time_app.book(day, slot_time, member_id)
        except ValidationError as exc:
            return _error("BAD_REQUEST", str(exc), 400)
        except NotFoundError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        except ServiceUnavailableError:
            return _unavailable()
        return jsonify(_tee_time_json(slot)), 201

    return app


def launch() -> Flask:
    """Build ClubStorage + TeeTimeApp + Flask from DATABASE_PATH."""
    settings = ensure_settings()
    storage = ClubStorage(settings["DATABASE_PATH"])
    try:
        storage.create_schema()
        storage.ping()
    except DatabaseUnavailableError as exc:
        raise RuntimeError(
            "Database not reachable. Check DATABASE_PATH in .env. "
            f"Details: {exc}"
        ) from exc
    return create_app(TeeTimeApp(storage))


if __name__ == "__main__":
    try:
        app = launch()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    app.run(debug=True, port=5000)
