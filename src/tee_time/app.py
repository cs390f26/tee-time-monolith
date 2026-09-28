"""JSON routes for tee times and members.

Handlers check the request, call TeeTimeApp, and return JSON or HTML.
"""

import re
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

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SLOT_ID_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}):00")


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


def _parse_day(raw: str | None):
    """Return a date, or a 400 response when the query value is unusable."""
    if raw is None or not raw.strip():
        return None, _error("BAD_REQUEST", "date query parameter is required", 400)
    text = raw.strip()
    if _DATE_RE.fullmatch(text) is None:
        return None, _error("BAD_REQUEST", "date must be YYYY-MM-DD", 400)
    try:
        return date.fromisoformat(text), None
    except ValueError:
        return None, _error("BAD_REQUEST", "date must be YYYY-MM-DD", 400)


def _parse_slot_id(slot_id: str) -> tuple[date, str] | None:
    """Return (date, HH:MM), or None when the id is not a real slot."""
    match = _SLOT_ID_RE.fullmatch(slot_id)
    if match is None:
        return None
    slot_date, slot_time = match.group(1), match.group(2)
    try:
        parsed_day = date.fromisoformat(slot_date)
        time.fromisoformat(slot_time)
    except ValueError:
        return None
    return parsed_day, slot_time


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
        day, error = _parse_day(request.args.get("date"))
        if error is not None:
            return error
        try:
            slots = tee_time_app.list_tee_times(day)
        except ServiceUnavailableError:
            return _unavailable()
        return jsonify({"teeTimes": [_summary_json(slot) for slot in slots]}), 200

    @app.get("/tee-times/<slot_id>")
    def get_tee_time(slot_id):
        parsed = _parse_slot_id(slot_id)
        if parsed is None:
            return _error(
                "BAD_REQUEST",
                "tee time id must look like 2026-09-19T07:00:00",
                400,
            )
        day, slot_time = parsed
        try:
            slot = tee_time_app.get_tee_time(day, slot_time)
        except NotFoundError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        except ServiceUnavailableError:
            return _unavailable()
        return jsonify(_tee_time_json(slot)), 200

    @app.post("/members")
    def add_member():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _error("BAD_REQUEST", "JSON body required", 400)
        name = body.get("name")
        phone = body.get("phone")
        if not isinstance(name, str) or not isinstance(phone, str):
            return _error("BAD_REQUEST", "name and phone are required", 400)
        try:
            member_id = tee_time_app.add_member(name, phone)
        except ValidationError as exc:
            return _error("BAD_REQUEST", str(exc), 400)
        except ServiceUnavailableError:
            return _unavailable()
        return jsonify({"id": member_id}), 201

    @app.post("/tee-times/<slot_id>/bookings")
    def add_booking(slot_id):
        parsed = _parse_slot_id(slot_id)
        if parsed is None:
            return _error(
                "BAD_REQUEST",
                "tee time id must look like 2026-09-19T07:00:00",
                400,
            )
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("memberId"), str):
            return _error("BAD_REQUEST", "memberId is required", 400)
        member_id = body["memberId"].strip()
        if not member_id:
            return _error("BAD_REQUEST", "memberId must not be blank", 400)
        day, slot_time = parsed
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
