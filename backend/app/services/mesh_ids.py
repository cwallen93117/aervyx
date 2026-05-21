"""Helpers for normalizing Meshtastic node identifiers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MeshDevice, User


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


def mesh_device_display_name(device: MeshDevice, owner: User | None = None) -> str:
    """Return the operator-facing name for a registered Meshtastic device."""
    label = (device.label or "").strip()
    if label:
        return label
    owner_name = ((owner.full_name if owner else None) or (owner.username if owner else None) or "").strip()
    if owner_name:
        return owner_name
    return normalize_mesh_device_id(device.device_id) or device.device_id


def resolve_mesh_device_display_names(session: Session, device_ids: set[str | None] | list[str | None]) -> dict[str, str]:
    """Resolve Meshtastic node IDs to registered device labels when possible."""
    normalized_ids = {normalized for raw in device_ids if (normalized := normalize_mesh_device_id(raw)) is not None}
    lookup_ids = {
        candidate
        for device_id in normalized_ids
        for candidate in mesh_device_id_lookup_variants(device_id)
    }
    if not lookup_ids:
        return {}

    devices = session.scalars(select(MeshDevice).where(MeshDevice.device_id.in_(lookup_ids))).all()
    owner_ids = {device.owner_user_id for device in devices}
    owners = {
        owner.id: owner
        for owner in session.scalars(select(User).where(User.id.in_(owner_ids))).all()
    } if owner_ids else {}

    display_by_id: dict[str, str] = {}
    for device in devices:
        display = mesh_device_display_name(device, owners.get(device.owner_user_id))
        for variant in mesh_device_id_lookup_variants(device.device_id):
            display_by_id[variant] = display
        canonical = normalize_mesh_device_id(device.device_id)
        if canonical:
            display_by_id[canonical] = display

    return display_by_id
