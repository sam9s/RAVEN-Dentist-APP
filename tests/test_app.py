"""Smoke tests for FastAPI application."""

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    """Health endpoint should return status ok."""

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_endpoint() -> None:
    """Version endpoint should expose application version."""

    response = client.get("/version")
    assert response.status_code == 200
    assert "version" in response.json()
