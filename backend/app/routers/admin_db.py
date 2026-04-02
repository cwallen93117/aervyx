"""Admin endpoints for database export/import between environments."""

import gzip
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.deps import require_admin
from app.models import User

router = APIRouter(prefix="/api/admin/db", tags=["admin-db"])

ANONYMIZE_SQL = """
BEGIN;
UPDATE users SET
  password_hash = 'redacted',
  oauth_id = NULL,
  oauth_provider = NULL
WHERE password_hash IS NOT NULL OR oauth_id IS NOT NULL;

UPDATE pilots SET
  email = 'pilot_' || id || '@test.aervyx.net',
  first_name = 'Pilot',
  last_name = 'P' || id
WHERE email IS NOT NULL;
COMMIT;
"""


def _pg_env() -> dict[str, str]:
    """Build env dict with PGPASSWORD from the database URL."""
    import os

    settings = get_settings()
    parsed = urlparse(settings.database_url)
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = parsed.password
    return env


def _pg_conn_args() -> list[str]:
    """Return ['-h', host, '-p', port, '-U', user, dbname] from database URL."""
    settings = get_settings()
    parsed = urlparse(settings.database_url)
    args = []
    if parsed.hostname:
        args += ["-h", parsed.hostname]
    if parsed.port:
        args += ["-p", str(parsed.port)]
    if parsed.username:
        args += ["-U", parsed.username]
    dbname = parsed.path.lstrip("/")
    args.append(dbname)
    return args


@router.get("/export")
def export_database(
    anonymize: bool = Query(False, description="Anonymize PII before exporting"),
    _admin: User = Depends(require_admin),
):
    """Download a gzipped pg_dump of the current database."""
    env = _pg_env()
    conn = _pg_conn_args()

    if anonymize:
        psql = subprocess.run(
            ["psql", *conn],
            input=ANONYMIZE_SQL,
            capture_output=True,
            text=True,
            env=env,
        )
        if psql.returncode != 0:
            raise HTTPException(500, f"Anonymization failed: {psql.stderr[:500]}")

    def _stream():
        proc = subprocess.Popen(
            ["pg_dump", *conn],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        compressor = gzip.open(proc.stdout, mode="rb")  # type: ignore[arg-type]
        # Stream raw pg_dump output through gzip
        buf = bytearray()
        for chunk in iter(lambda: proc.stdout.read(64 * 1024), b""):  # type: ignore[union-attr]
            buf.clear()
            buf.extend(gzip.compress(chunk))
            yield bytes(buf)
        proc.wait()

    return StreamingResponse(
        _stream(),
        media_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=aervyx-db-export.sql.gz"},
    )


@router.post("/import")
def import_database(
    file: UploadFile = File(...),
    confirm: str = Query(..., description="Must be 'yes' to proceed"),
    _admin: User = Depends(require_admin),
):
    """Upload a gzipped SQL dump and restore it. DESTRUCTIVE — overwrites the database."""
    if confirm != "yes":
        raise HTTPException(400, "Import requires ?confirm=yes to prevent accidental data loss")

    env = _pg_env()
    conn = _pg_conn_args()

    with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = Path(tmp.name)

    try:
        sql = gzip.decompress(tmp_path.read_bytes())
        result = subprocess.run(
            ["psql", "--quiet", "--single-transaction", *conn],
            input=sql,
            capture_output=True,
            env=env,
        )
        if result.returncode != 0:
            raise HTTPException(500, f"Restore failed: {result.stderr.decode()[:500]}")
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"status": "ok", "message": "Database imported successfully"}
