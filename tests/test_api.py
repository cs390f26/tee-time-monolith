from datetime import date
import pytest
from sample_data import make_sample_member, make_sample_slot, make_sample_slot_view
from tee_time.store import (
    MemberAlreadyExistsError,
    PlayerAlreadyBookedError,
    PositionTakenError,
    SlotFullError,
)
from tee_time.types import MemberView


def test_list_members(client, mock_app):
    mock_app.list_members.return_value = [
        MemberView(id="mem_01", name="Alice Smith", phone="555-0100")
    ]

    response = client.get("/members", headers={"Accept": "application/json"})
    assert response.status_code == 200

    json_data = response.get_json()
    assert json_data is not None, "Expected JSON response, but got None"

    assert "members" in json_data
    assert len(json_data["members"]) == 1
    assert json_data["members"][0]["id"] == "mem_01"


def test_add_member_success(client, mock_app):
    mock_app.add_member.return_value = "m1"
    payload = {"id": "m1", "name": "Alice", "phone": "555-0100"}
    response = client.post("/members", json=payload)
    assert response.status_code == 201


def test_add_member_already_exists(client, mock_app):
    mock_app.add_member.side_effect = MemberAlreadyExistsError("exists")
    with pytest.raises(MemberAlreadyExistsError):
        client.post(
            "/members", json={"id": "m1", "name": "Alice", "phone": "555-0100"}
        )


def test_get_tee_time_success(client, mock_app):
    mock_app.get_tee_time.return_value = make_sample_slot_view()
    response = client.get("/tee-times/2026-09-19T07:00:00")
    assert response.status_code == 200


def test_add_booking_success(client, mock_app):
    mock_app.add_booking.return_value = make_sample_slot_view()
    if hasattr(mock_app, "book"):
        mock_app.book.return_value = make_sample_slot_view()

    response = client.post(
        "/tee-times/2026-09-19T07:00:00/bookings",
        json={"memberId": "m1", "playerNumber": 1},
    )
    assert response.status_code in (200, 201)


def test_add_booking_errors(client, mock_app):
    mock_app.book.side_effect = SlotFullError("full")
    if hasattr(mock_app, "add_booking"):
        mock_app.add_booking.side_effect = SlotFullError("full")

    with pytest.raises(SlotFullError):
        client.post(
            "/tee-times/2026-09-19T07:00:00/bookings", json={"memberId": "m1"}
        )