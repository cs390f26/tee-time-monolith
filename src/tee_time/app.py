"""JSON routes for tee times and members.

Storage and booking rules come later. These handlers check the request
and return the JSON shapes the pages will use.
"""

import re
import secrets
from datetime import date, time

from flask import Flask, jsonify, render_template, request

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SLOT_ID_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}):00")


def _error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


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


def _parse_slot_id(slot_id: str) -> tuple[str, str] | None:
    """Return (YYYY-MM-DD, HH:MM), or None when the id is not a real slot."""
    match = _SLOT_ID_RE.fullmatch(slot_id)
    if match is None:
        return None
    slot_date, slot_time = match.group(1), match.group(2)
    try:
        date.fromisoformat(slot_date)
        time.fromisoformat(slot_time)
    except ValueError:
        return None
    return slot_date, slot_time


def _slot_json(slot_id: str, slot_date: str, slot_time: str) -> dict:
    """Players already on the slot, then members the book page can still pick."""
    return {
        "id": slot_id,
        "date": slot_date,
        "time": slot_time,
        "players": [],
        "playerCount": 0,
        "bookable": True,
        "availableMembers": [],
    }


def create_app() -> Flask:
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
            return jsonify({"upcoming": [], "past": []}), 200
        return render_template("reserved.html")

    @app.get("/members")
    def members_page():
        if _wants_json():
            return jsonify({"members": []}), 200
        return render_template("members.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.get("/tee-times")
    def list_tee_times():
        _day, error = _parse_day(request.args.get("date"))
        if error is not None:
            return error
        return jsonify({"teeTimes": []}), 200

    @app.get("/tee-times/<slot_id>")
    def get_tee_time(slot_id):
        parsed = _parse_slot_id(slot_id)
        if parsed is None:
            return _error(
                "BAD_REQUEST",
                "tee time id must look like 2026-09-19T07:00:00",
                400,
            )
        slot_date, slot_time = parsed
        return jsonify(_slot_json(slot_id, slot_date, slot_time)), 200

    @app.post("/members")
    def add_member():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _error("BAD_REQUEST", "JSON body required", 400)
        name = body.get("name")
        phone = body.get("phone")
        if not isinstance(name, str) or not isinstance(phone, str):
            return _error("BAD_REQUEST", "name and phone are required", 400)
        if not name.strip() or not phone.strip():
            return _error("BAD_REQUEST", "name and phone must not be blank", 400)
        return jsonify({"id": secrets.token_hex(4)}), 201

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
        if not body["memberId"].strip():
            return _error("BAD_REQUEST", "memberId must not be blank", 400)
        slot_date, slot_time = parsed
        return jsonify(_slot_json(slot_id, slot_date, slot_time)), 201

    return app


def launch() -> Flask:
    """Build the Flask app. Wiring a database comes later."""
    return create_app()


if __name__ == "__main__":
    launch().run(debug=True, port=5000)
