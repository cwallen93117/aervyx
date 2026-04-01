#!/usr/bin/env python3
"""GitHub webhook listener that dispatches deploys for multiple branches.

Configuration via environment variables:
  BRANCH_MAP  – comma-separated "branch:script" pairs, e.g.
                "main:/path/deploy-prod.sh,staging:/path/deploy-staging.sh"
  BRANCH / DEPLOY_SCRIPT – legacy single-branch fallback (used when BRANCH_MAP is empty)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9100"))
DEPLOY_PATH = os.environ.get("DEPLOY_PATH", "/github/deploy-staging")
REPO_DIR = os.environ.get("REPO_DIR", "/srv/aervyx-staging/repo")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# Multi-branch support: parse BRANCH_MAP or fall back to single BRANCH/DEPLOY_SCRIPT
BRANCH_MAP: dict[str, str] = {}
_raw_map = os.environ.get("BRANCH_MAP", "").strip()
if _raw_map:
    for entry in _raw_map.split(","):
        entry = entry.strip()
        if ":" in entry:
            branch, script = entry.split(":", 1)
            BRANCH_MAP[branch.strip()] = script.strip()
else:
    # Legacy single-branch fallback
    _branch = os.environ.get("BRANCH", "staging")
    _script = os.environ.get(
        "DEPLOY_SCRIPT", "/srv/aervyx-staging/repo/deploy/staging/deploy-staging.sh"
    )
    BRANCH_MAP[_branch] = _script


def _verify_signature(raw_body: bytes, header_value: str | None) -> bool:
    if not WEBHOOK_SECRET or not header_value or not header_value.startswith("sha256="):
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    actual = header_value.split("=", 1)[1]
    return hmac.compare_digest(expected, actual)


class WebhookHandler(BaseHTTPRequestHandler):
    server_version = "AervyxWebhook/2.0"

    def log_message(self, fmt: str, *args) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)

    def _respond(self, status: HTTPStatus, body: dict[str, str]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._respond(HTTPStatus.OK, {"status": "ok"})
            return
        self._respond(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != DEPLOY_PATH:
            self._respond(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if not _verify_signature(raw_body, self.headers.get("X-Hub-Signature-256")):
            self._respond(HTTPStatus.UNAUTHORIZED, {"error": "invalid signature"})
            return

        event_name = self.headers.get("X-GitHub-Event", "")
        if event_name == "ping":
            self._respond(HTTPStatus.OK, {"status": "pong"})
            return
        if event_name != "push":
            self._respond(HTTPStatus.ACCEPTED, {"status": "ignored"})
            return

        payload = json.loads(raw_body.decode("utf-8") or "{}")
        ref = payload.get("ref", "")

        for branch, script in BRANCH_MAP.items():
            if ref == f"refs/heads/{branch}":
                env = os.environ.copy()
                env["GITHUB_DELIVERY_ID"] = self.headers.get("X-GitHub-Delivery", "")
                subprocess.Popen(
                    [script],
                    cwd=REPO_DIR,
                    env=env,
                    start_new_session=True,
                )
                logging.info("Deploy started for branch %s via %s", branch, script)
                self._respond(
                    HTTPStatus.ACCEPTED,
                    {"status": "deploy started", "ref": ref, "branch": branch},
                )
                return

        self._respond(
            HTTPStatus.ACCEPTED,
            {"status": "ignored", "reason": f"no matching branch for {ref}"},
        )


def main() -> None:
    if not WEBHOOK_SECRET:
        raise SystemExit("WEBHOOK_SECRET must be set")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    branches = ", ".join(BRANCH_MAP.keys())
    logging.info(
        "Listening on http://%s:%s%s for branches: %s",
        LISTEN_HOST, LISTEN_PORT, DEPLOY_PATH, branches,
    )
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), WebhookHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
