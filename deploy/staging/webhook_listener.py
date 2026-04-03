#!/usr/bin/env python3
"""GitHub webhook listener that dispatches deploys for multiple branches.

Configuration via environment variables:
  BRANCH_MAP  – comma-separated "branch:script" pairs, e.g.
                "main:/path/deploy-prod.sh,staging:/path/deploy-staging.sh"
  BRANCH / DEPLOY_SCRIPT – legacy single-branch fallback (used when BRANCH_MAP is empty)

Features:
  - Per-branch deploy queue: if a push arrives while a deploy is running,
    the latest push is queued and auto-dispatched when the active deploy finishes.
  - Only the most recent pending push per branch is kept (older ones are superseded).
  - Thread-safe: all queue state is protected by a lock.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
import threading
import time
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


# ---------------------------------------------------------------------------
# Deploy queue: ensures back-to-back pushes don't get lost
# ---------------------------------------------------------------------------
_queue_lock = threading.Lock()
# branch -> True if a deploy is currently running
_active_deploys: dict[str, bool] = {}
# branch -> env dict for the most recent pending push (only latest is kept)
_pending_deploys: dict[str, dict[str, str]] = {}


def _run_deploy(branch: str, script: str, env: dict[str, str]) -> None:
    """Run a deploy and, when it finishes, check if another push arrived while it was running."""
    try:
        logging.info("Deploy executing for branch %s via %s", branch, script)
        process = subprocess.Popen(
            [script],
            cwd=REPO_DIR,
            env=env,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        stdout, _ = process.communicate(timeout=600)  # 10 minute timeout
        exit_code = process.returncode
        if exit_code == 0:
            logging.info("Deploy finished successfully for branch %s", branch)
        else:
            output_tail = (stdout or b"")[-500:].decode("utf-8", errors="replace")
            logging.warning(
                "Deploy failed for branch %s (exit %d): ...%s",
                branch, exit_code, output_tail,
            )
    except subprocess.TimeoutExpired:
        logging.error("Deploy timed out for branch %s after 600s — killing", branch)
        process.kill()
        process.wait()
    except Exception:
        logging.exception("Deploy crashed for branch %s", branch)

    # Check if a newer push arrived while we were deploying
    with _queue_lock:
        pending_env = _pending_deploys.pop(branch, None)
        if pending_env is not None:
            logging.info("Queued deploy found for branch %s — starting follow-up", branch)
            # Keep the branch marked as active and start the queued deploy
            thread = threading.Thread(
                target=_run_deploy,
                args=(branch, script, pending_env),
                daemon=True,
            )
            thread.start()
        else:
            _active_deploys[branch] = False


def dispatch_deploy(branch: str, script: str, env: dict[str, str]) -> str:
    """Dispatch a deploy, queuing it if one is already running for this branch.

    Returns a status string for the webhook response.
    """
    with _queue_lock:
        if _active_deploys.get(branch):
            # A deploy is already running — queue this one (supersedes any older pending)
            _pending_deploys[branch] = env
            logging.info(
                "Deploy already running for branch %s — queued (delivery %s)",
                branch, env.get("GITHUB_DELIVERY_ID", "?"),
            )
            return "queued"
        else:
            _active_deploys[branch] = True

    thread = threading.Thread(
        target=_run_deploy,
        args=(branch, script, env),
        daemon=True,
    )
    thread.start()
    return "started"


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------
def _verify_signature(raw_body: bytes, header_value: str | None) -> bool:
    if not WEBHOOK_SECRET or not header_value or not header_value.startswith("sha256="):
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    actual = header_value.split("=", 1)[1]
    return hmac.compare_digest(expected, actual)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class WebhookHandler(BaseHTTPRequestHandler):
    server_version = "AervyxWebhook/3.0"

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
            with _queue_lock:
                active = [b for b, running in _active_deploys.items() if running]
                pending = list(_pending_deploys.keys())
            health: dict[str, str] = {"status": "ok"}
            if active:
                health["active_deploys"] = ",".join(active)
            if pending:
                health["pending_deploys"] = ",".join(pending)
            self._respond(HTTPStatus.OK, health)
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
                deploy_status = dispatch_deploy(branch, script, env)
                logging.info(
                    "Deploy %s for branch %s (delivery %s)",
                    deploy_status, branch, env["GITHUB_DELIVERY_ID"],
                )
                self._respond(
                    HTTPStatus.ACCEPTED,
                    {"status": f"deploy {deploy_status}", "ref": ref, "branch": branch},
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
