from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import require_admin
from app.models import User
from app.routers import provisioner_release


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        provisioner_release,
        "get_settings",
        lambda: SimpleNamespace(provisioner_root=str(tmp_path)),
    )
    app = FastAPI()
    app.include_router(provisioner_release.router)

    def override_admin() -> User:
        return User(id=1, username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")

    app.dependency_overrides[require_admin] = override_admin
    return TestClient(app)


def test_upload_and_download_admin_provisioner_release(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    upload = client.post(
        "/api/provisioner/upload",
        files={"file": ("provisioner.zip", b"fake-zip", "application/zip")},
        data={"version": "0.1.0", "release_notes": "Initial desktop provisioner"},
    )

    assert upload.status_code == 200
    version = client.get("/api/provisioner/version")
    assert version.status_code == 200
    assert version.json()["version"] == "0.1.0"
    assert version.json()["filename"] == "AervyxMeshtasticProvisioner-0.1.0-win-x64.zip"

    download = client.get("/api/provisioner/download")
    assert download.status_code == 200
    assert download.content == b"fake-zip"


def test_upload_rejects_non_release_file(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    response = client.post(
        "/api/provisioner/upload",
        files={"file": ("notes.txt", b"nope", "text/plain")},
        data={"version": "0.1.0"},
    )

    assert response.status_code == 400
