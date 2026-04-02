"""Pilot deduplication registry backed by the Aervyx API."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from audit.api_client import AervyxClient
from audit.fsdb_parser import FsdbParticipant

log = logging.getLogger(__name__)


@dataclass
class CachedPilot:
    id: int
    first_name: str
    last_name: str
    civl_id: str


def _normalize(name: str) -> str:
    return " ".join(name.lower().split())


class PilotRegistry:
    """Maintains a local cache of all pilots and deduplicates on insert."""

    def __init__(self, client: AervyxClient):
        self.client = client
        self.by_civl_id: dict[str, CachedPilot] = {}
        self.by_name: dict[str, list[CachedPilot]] = {}
        self._load()

    def _load(self) -> None:
        pilots = self.client.list_all_pilots()
        for p in pilots:
            cp = CachedPilot(
                id=p["id"],
                first_name=p.get("first_name", ""),
                last_name=p.get("last_name", ""),
                civl_id=p.get("civl_id") or "",
            )
            self._index(cp)
        log.info("Loaded %d existing pilots into registry", len(pilots))

    def _index(self, cp: CachedPilot) -> None:
        if cp.civl_id:
            self.by_civl_id[cp.civl_id] = cp
        key = _normalize(f"{cp.first_name} {cp.last_name}")
        self.by_name.setdefault(key, []).append(cp)

    def find_or_create(self, p: FsdbParticipant, event_id: int) -> int:
        """Return the Aervyx pilot ID, creating if needed, and assign to event."""
        existing = self._find(p)
        if existing:
            log.info("Matched pilot %r → existing id=%d", p.name, existing.id)
            try:
                self.client.assign_pilot(event_id, existing.id)
            except Exception as exc:
                # Already assigned is fine
                if "already" not in str(exc).lower() and "409" not in str(exc):
                    log.warning("assign_pilot failed for %d: %s", existing.id, exc)
            return existing.id

        # Create new pilot
        parts = p.name.split(None, 1)
        first_name = parts[0] if parts else p.name
        last_name = parts[1] if len(parts) > 1 else ""

        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "nation": p.nation or None,
            "civl_id": p.civl_id or None,
        }
        resp = self.client.create_pilot(event_id, payload)
        pilot_id = resp["id"]
        cp = CachedPilot(
            id=pilot_id,
            first_name=first_name,
            last_name=last_name,
            civl_id=p.civl_id or "",
        )
        self._index(cp)
        log.info("Created pilot %r → id=%d", p.name, pilot_id)
        return pilot_id

    def _find(self, p: FsdbParticipant) -> CachedPilot | None:
        # Try CIVL ID first
        if p.civl_id:
            match = self.by_civl_id.get(p.civl_id)
            if match:
                return match

        # Try exact name match
        key = _normalize(p.name)
        candidates = self.by_name.get(key, [])
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            log.warning("Ambiguous name match for %r (%d candidates)", p.name, len(candidates))

        return None
