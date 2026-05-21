"""Helpers for normalizing Meshtastic node identifiers."""

from __future__ import annotations


def normalize_mesh_device_id(value: str | None) -> str | None:
    """Return Aervyx's canonical Meshtastic node id form.

    Official Meshtastic node IDs are commonly displayed as ``!`` plus eight
    hexadecimal digits.  Users often copy only the hex suffix, so normalize
    that case before the value is used for MQTT topics or assignment lookups.
    """
    candidate = (value or "").strip().lower()
    if not candidate:
        return None
    if candidate.startswith("!"):
        return candidate
    if len(candidate) == 8 and all(ch in "0123456789abcdef" for ch in candidate):
        return f"!{candidate}"
    return candidate


def mesh_device_id_lookup_variants(value: str | None) -> list[str]:
    """Return canonical and legacy forms for a Meshtastic node id."""
    normalized = normalize_mesh_device_id(value)
    if not normalized:
        return []

    variants = [normalized]
    if normalized.startswith("!"):
        suffix = normalized[1:]
        if len(suffix) == 8 and all(ch in "0123456789abcdef" for ch in suffix):
            variants.append(suffix)

    seen: set[str] = set()
    return [variant for variant in variants if not (variant in seen or seen.add(variant))]
