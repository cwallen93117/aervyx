"""APK release hosting — version check, download, and admin upload."""

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

router = APIRouter(prefix="/api/app", tags=["app-release"])

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


# ── helpers ────────────────────────────────────────────────────────

def _releases_path() -> Path:
    return Path(get_settings().apk_root) / "releases.json"


def _read_releases() -> list[dict]:
    path = _releases_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_releases(releases: list[dict]) -> None:
    path = _releases_path()
    path.write_text(json.dumps(releases, indent=2), encoding="utf-8")


def _latest_release() -> dict | None:
    releases = _read_releases()
    return releases[-1] if releases else None


# ── schemas ────────────────────────────────────────────────────────

class AppVersionResponse(BaseModel):
    version: str
    version_code: int
    download_url: str
    release_notes: str
    release_date: str
    min_supported_version: str
    file_size_bytes: int | None = None


# ── endpoints ──────────────────────────────────────────────────────

@router.get("/version")
def get_version() -> AppVersionResponse:
    """Return metadata for the latest release.  Public — no auth."""
    release = _latest_release()
    if release is None:
        raise HTTPException(status_code=404, detail="No releases available")

    settings = get_settings()
    return AppVersionResponse(
        version=release["version"],
        version_code=release["version_code"],
        download_url=f"{settings.api_public_url}/api/app/download",
        release_notes=release.get("release_notes", ""),
        release_date=release["release_date"],
        min_supported_version=release.get("min_supported_version", release["version"]),
        file_size_bytes=release.get("file_size_bytes"),
    )


@router.get("/releases")
def list_releases() -> list[AppVersionResponse]:
    """Return metadata for all releases, newest first.  Public — no auth."""
    releases = _read_releases()
    if not releases:
        return []

    settings = get_settings()
    # releases.json stores oldest first (append order) — reverse so newest is first
    return [
        AppVersionResponse(
            version=release["version"],
            version_code=release["version_code"],
            download_url=f"{settings.api_public_url}/api/app/download",
            release_notes=release.get("release_notes", ""),
            release_date=release["release_date"],
            min_supported_version=release.get("min_supported_version", release["version"]),
            file_size_bytes=release.get("file_size_bytes"),
        )
        for release in reversed(releases)
    ]


@router.get("/download")
def download_apk():
    """Serve the latest APK.  Public — no auth."""
    release = _latest_release()
    if release is None:
        raise HTTPException(status_code=404, detail="No releases available")

    settings = get_settings()
    apk_path = Path(settings.apk_root) / release["version"] / release["apk_filename"]
    if not apk_path.exists():
        raise HTTPException(status_code=404, detail="APK file not found")

    # Always serve with version+build in the filename so users can verify what
    # they downloaded matches the displayed version on /app.
    served_name = f"aervyx-{release['version']}+{release['version_code']}.apk"

    return FileResponse(
        path=str(apk_path),
        media_type="application/vnd.android.package-archive",
        filename=served_name,
    )


@router.post("/upload")
def upload_apk(
    file: UploadFile = File(...),
    version: str = Form(...),
    version_code: int = Form(...),
    release_notes: str = Form(""),
    min_supported_version: str = Form("0.1.0"),
    _admin: User = Depends(require_admin),
):
    """Upload a new APK release.  Admin only."""
    if not _SEMVER.match(version):
        raise HTTPException(status_code=400, detail="Version must be semver (e.g. 1.0.0)")

    settings = get_settings()
    version_dir = Path(settings.apk_root) / version
    version_dir.mkdir(parents=True, exist_ok=True)

    apk_filename = f"aervyx-{version}+{version_code}.apk"
    apk_path = version_dir / apk_filename

    content = file.file.read()
    apk_path.write_bytes(content)

    release_entry = {
        "version": version,
        "version_code": version_code,
        "release_notes": release_notes,
        "release_date": datetime.now(timezone.utc).isoformat(),
        "min_supported_version": min_supported_version,
        "file_size_bytes": len(content),
        "apk_filename": apk_filename,
    }

    releases = _read_releases()
    # Replace if same version exists, otherwise append
    releases = [r for r in releases if r["version"] != version]
    releases.append(release_entry)
    _write_releases(releases)

    return {"status": "ok", "release": release_entry}
