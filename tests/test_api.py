from tee_time.tee_time import NotFoundError, ServiceUnavailableError
from tee_time.types import MemberView


def test_health_ok(client, mock_tee_time_app):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    mock_tee_time_app.health.assert_called_once()


def test_health_unavailable(client, mock_tee_time_app):
    mock_tee_time_app.health.side_effect = ServiceUnavailableError("DB down")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json == {"status": "unavailable"}


def test_list_members_json(client, mock_tee_time_app):
    mock_tee_time_app.list_members.return_value = [
        MemberView(id="m1", name="Alice", phone="555-0100")
    ]
    response = client.get("/members", headers={"Accept": "application/json"})
    assert response.status_code == 200
    assert response.json == {
        "members": [{"id": "m1", "name": "Alice", "phone": "555-0100"}]
    }


def test_get_tee_time_not_found(client, mock_tee_time_app):
    mock_tee_time_app.get_tee_time.side_effect = NotFoundError("Slot not found")
    response = client.get("/tee-times/2026-09-19T07:00:00")
    assert response.status_code == 404
    assert response.json["error"]["code"] == "NOT_FOUND"


def test_add_member_invalid_json(client):
    response = client.post("/members", json={"name": "Alice"})  # missing phone
    assert response.status_code == 400
    assert response.json["error"]["code"] == "BAD_REQUEST"