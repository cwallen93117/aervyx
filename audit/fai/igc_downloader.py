"""Download and extract IGC track files from competition platforms."""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from audit.fai.scraper_common import get_session

log = logging.getLogger(__name__)

# Base directory for downloaded data
DATA_DIR = Path(__file__).parent / "data"


def download_and_extract(
    url: str,
    dest_dir: Path,
    timeout: int = 300,
) -> list[Path]:
    """Download a ZIP file and extract IGC files to dest_dir.

    Returns list of extracted IGC file paths.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Check if we already have IGC files (skip re-download)
    existing = list(dest_dir.glob("*.igc")) + list(dest_dir.glob("*.IGC"))
    if existing:
        log.info("  Already have %d IGC files in %s, skipping download", len(existing), dest_dir)
        return _collect_igc(dest_dir)

    # Download
    zip_path = dest_dir / "tracks.zip"
    log.info("  Downloading %s → %s", url, zip_path)
    session = get_session()
    try:
        resp = session.get(url, timeout=timeout, stream=True)
        resp.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        log.info("  Downloaded %.1f MB", zip_path.stat().st_size / 1024 / 1024)
    except Exception as exc:
        log.warning("  Download failed: %s", exc)
        if zip_path.exists():
            zip_path.unlink()
        return []

    # Extract
    try:
        with zipfile.ZipFile(zip_path) as zf:
            igc_count = 0
            for name in zf.namelist():
                if name.lower().endswith(".igc"):
                    # Extract to flat directory (strip nested paths)
                    basename = Path(name).name
                    target = dest_dir / basename
                    if not target.exists():
                        target.write_bytes(zf.read(name))
                        igc_count += 1
            log.info("  Extracted %d IGC files", igc_count)
    except zipfile.BadZipFile:
        log.warning("  Bad ZIP file: %s", zip_path)
        return []
    finally:
        # Clean up ZIP to save space
        if zip_path.exists():
            zip_path.unlink()

    return _collect_igc(dest_dir)


def _collect_igc(folder: Path) -> list[Path]:
    """Collect all IGC files from a folder."""
    files = list(folder.glob("*.igc")) + list(folder.glob("*.IGC"))
    seen: set[str] = set()
    unique: list[Path] = []
    for f in sorted(files, key=lambda p: p.name.lower()):
        key = str(f).lower()
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def get_task_igc_dir(event_slug: str, task_id: int) -> Path:
    """Get the directory for a task's IGC files."""
    return DATA_DIR / event_slug / f"task_{task_id}"
