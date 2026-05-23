"""Admin-only desktop provisioner release hosting."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.deps import require_admin
from app.models import User

router = APIRouter(prefix="/api/provisioner", tags=["provisioner-release"])

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_ALLOWED_SUFFIXES = {".zip", ".exe"}


class ProvisionerVersionResponse(BaseModel):
    version: str
    filename: str
    release_notes: str
    release_date: str
    file_size_bytes: int | None = None


def _root() -> Path:
    root = Path(get_settings().provisioner_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _releases_path() -> Path:
    return _root() / "releases.json"


def _read_releases() -> list[dict]:
    path = _releases_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_releases(releases: list[dict]) -> None:
    _releases_path().write_text(json.dumps(releases, indent=2), encoding="utf-8")


def _latest_release() -> dict | None:
    releases = _read_releases()
    return releases[-1] if releases else None


def _response(release: dict) -> ProvisionerVersionResponse:
    return ProvisionerVersionResponse(
        version=release["version"],
        filename=release["filename"],
        release_notes=release.get("release_notes", ""),
        release_date=release["release_date"],
        file_size_bytes=release.get("file_size_bytes"),
    )


@router.get("/version")
def get_version(_admin: User = Depends(require_admin)) -> ProvisionerVersionResponse:
    release = _latest_release()
    if release is None:
        raise HTTPException(status_code=404, detail="No provisioner releases available")
    return _response(release)


@router.get("/releases")
def list_releases(_admin: User = Depends(require_admin)) -> list[ProvisionerVersionResponse]:
    return [_response(release) for release in reversed(_read_releases())]


@router.get("/download")
def download_provisioner(_admin: User = Depends(require_admin)):
    release = _latest_release()
    if release is None:
        raise HTTPException(status_code=404, detail="No provisioner releases available")
    path = _root() / release["version"] / release["filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Provisioner file not found")
    return FileResponse(path=str(path), media_type="application/octet-stream", filename=release["filename"])


@router.post("/upload")
def upload_provisioner(
    file: UploadFile = File(...),
    version: str = Form(...),
    release_notes: str = Form(""),
    _admin: User = Depends(require_admin),
):
    if not _SEMVER.match(version):
        raise HTTPException(status_code=400, detail="Version must be semver (e.g. 1.0.0)")
    source_name = Path(file.filename or "").name
    suffix = Path(source_name).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Provisioner release must be a .zip or .exe file")

    filename = f"AervyxMeshtasticProvisioner-{version}-win-x64{suffix}"
    version_dir = _root() / version
    version_dir.mkdir(parents=True, exist_ok=True)
    content = file.file.read()
    (version_dir / filename).write_bytes(content)

    release = {
        "version": version,
        "filename": filename,
        "release_notes": release_notes,
        "release_date": datetime.now(timezone.utc).isoformat(),
        "file_size_bytes": len(content),
    }
    releases = [item for item in _read_releases() if item["version"] != version]
    releases.append(release)
    _write_releases(releases)
    return {"status": "ok", "release": release}
