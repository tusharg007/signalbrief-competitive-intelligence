import pytest
from fastapi.testclient import TestClient

from signalbrief.api import create_app


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as value:
        yield value


def sign_in(client):
    csrf = client.get("/api/session").json()["csrf"]
    response = client.post("/api/login", json={"password": "a-secure-test-password"},
                           headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf"]}


def test_auth_and_csrf_boundaries(client, event):
    assert client.get("/api/runs").status_code == 401
    assert client.post("/events", json=event.model_dump(mode="json")).status_code == 401
    headers = sign_in(client)
    assert client.post("/api/events", json=event.model_dump(mode="json")).status_code == 403
    assert client.post("/api/events", json=event.model_dump(mode="json"), headers=headers).status_code == 202


def test_webhook_auth_payload_conflict_and_size(client, event):
    headers = {"X-API-Key": "k" * 40}
    body = event.model_dump(mode="json")
    response = client.post("/events", json=body, headers=headers)
    assert response.status_code == 202
    assert client.post("/events", json=body, headers=headers).json()["created"] is False
    body["title"] = "Different contents under the same event ID"
    assert client.post("/events", json=body, headers=headers).status_code == 409
    assert client.post("/events", content=b"x" * 70000, headers=headers).status_code == 413


def test_malicious_source_url_rejected_at_ingress(client, event):
    body = event.model_dump(mode="json")
    body["source_url"] = "https://127.0.0.1/internal"
    assert client.post("/events", json=body, headers={"X-API-Key": "k" * 40}).status_code == 422


def test_public_health_and_login_throttling(client):
    assert "runs" not in client.get("/health").json()
    csrf = client.get("/api/session").json()["csrf"]
    for _ in range(5):
        assert client.post("/api/login", json={"password": "incorrect"}, headers={"X-CSRF-Token": csrf}).status_code == 401
    assert client.post("/api/login", json={"password": "incorrect"}, headers={"X-CSRF-Token": csrf}).status_code == 429


def test_cross_origin_login_denied(client):
    assert client.post("/api/login", json={"password": "invalid"}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_report_export_and_stale_review(client, ready_run):
    headers = sign_in(client)
    response = client.get(f"/api/runs/{ready_run}/report.md")
    assert response.status_code == 200
    assert "https://linear.app/changelog" in response.text
    assert "hypotheses" in response.text
    assert client.post(f"/api/runs/{ready_run}/review", json={"decision": "approve", "version": 2}, headers=headers).status_code == 409
    assert client.post(f"/api/runs/{ready_run}/review", json={"decision": "approve", "version": 1}, headers=headers).status_code == 200
