from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_removed_challenge_routes_return_not_found() -> None:
    client = TestClient(app)
    for method, path in (
        ("GET", "/api/challenges"),
        ("POST", "/api/challenges"),
        ("GET", "/api/public/challenges/retired-slug"),
        ("GET", "/api/auth/challenge-settings"),
        ("PATCH", "/api/auth/challenge-settings"),
        ("POST", "/api/auth/challenge-settings/turnpoints/upload"),
    ):
        assert client.request(method, path).status_code == 404
