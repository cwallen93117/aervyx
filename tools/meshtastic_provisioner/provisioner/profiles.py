"""Profile loading, validation, and target config rendering."""

from __future__ import annotations

import base64
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .schema import PROFILE_KEYS, format_position_flags, get_path


REQUIRED_PREFIX = "__REQUIRED_"


def _resources_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "provisioner" / "resources"
    return Path(__file__).resolve().parent / "resources"


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def user_profile_path() -> Path:
    env_path = os.environ.get("AERVYX_PROVISIONER_PROFILE")
    if env_path:
        return Path(env_path)
    if getattr(sys, "frozen", False):
        return _exe_dir() / "aervyx_profiles.local.yaml"
    return Path(__file__).resolve().parents[1] / "profiles" / "aervyx_profiles.local.yaml"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping.")
    return data


def _overlay_candidates() -> list[Path]:
    candidates: list[Path] = []
    env_path = os.environ.get("AERVYX_PROVISIONER_PROFILE")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            _exe_dir() / "aervyx_profiles.local.yaml",
            _resources_dir() / "aervyx_profiles.local.yaml",
            Path(__file__).resolve().parents[1] / "profiles" / "aervyx_profiles.local.yaml",
        ]
    )
    return candidates


def load_profile_bundle() -> dict[str, Any]:
    bundle = _read_yaml(_resources_dir() / "aervyx_profiles.yaml")
    for candidate in _overlay_candidates():
        if candidate.exists():
            bundle = _deep_merge(bundle, _read_yaml(candidate))
    _validate_bundle_shape(bundle)
    return bundle


def save_profile_bundle(bundle: dict[str, Any]) -> Path:
    path = user_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": bundle.get("version", 1),
        "app_version": bundle.get("app_version"),
        "profiles": bundle.get("profiles", {}),
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")
    return path


def _validate_bundle_shape(bundle: dict[str, Any]) -> None:
    profiles = bundle.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError("Profile bundle is missing a 'profiles' mapping.")
    missing = [key for key in PROFILE_KEYS if key not in profiles]
    if missing:
        raise ValueError(f"Profile bundle is missing profile(s): {', '.join(missing)}")


def profile_settings(bundle: dict[str, Any], profile_key: str) -> dict[str, Any]:
    try:
        profile = bundle["profiles"][profile_key]
    except KeyError as exc:
        raise KeyError(f"Unknown profile: {profile_key}") from exc
    settings = profile.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError(f"Profile {profile_key} has no settings mapping.")
    return deepcopy(settings)


def display_value(bundle: dict[str, Any], profile_key: str, path: str, secret: bool = False) -> str:
    value = get_path(profile_settings(bundle, profile_key), path, "")
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if path.endswith("position_flags"):
        return format_position_flags(int(value or 0))
    return str(value)


def build_target_config(bundle: dict[str, Any], profile_key: str, long_name: str, short_name: str) -> dict[str, Any]:
    if not long_name.strip():
        raise ValueError("Name is required.")
    if not short_name.strip():
        raise ValueError("Shortname is required.")
    if len(short_name.strip()) > 5:
        raise ValueError("Shortname must be 5 characters or fewer for Meshtastic.")

    target = profile_settings(bundle, profile_key)
    target["owner"] = long_name.strip()
    target["owner_short"] = short_name.strip()
    _prune_unused_wifi_credentials(target)
    return target


def _prune_unused_wifi_credentials(target: dict[str, Any]) -> None:
    network = target.get("config", {}).get("network", {})
    if not network.get("wifi_enabled"):
        network.pop("wifi_ssid", None)
        network.pop("wifi_psk", None)


def required_placeholders(target: dict[str, Any]) -> list[str]:
    missing: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{path}.{key}" if path else key)
        elif isinstance(value, str) and value.startswith(REQUIRED_PREFIX):
            missing.append(path)

    walk(target, "")
    return missing


def decode_psk(value: str | bytes | None) -> bytes:
    if value is None:
        return b"\x01"
    if isinstance(value, bytes):
        return value
    raw = value.strip()
    if not raw or raw.lower() == "default":
        return b"\x01"
    if raw.lower() == "none":
        return b""
    if raw.lower().startswith("base64:"):
        return base64.b64decode(raw.split(":", 1)[1])
    if raw.lower().startswith("0x"):
        return bytes.fromhex(raw[2:])
    return base64.b64decode(raw)


def encode_psk(value: bytes | None) -> str:
    if value is None or value == b"\x01":
        return "default"
    if value == b"":
        return "none"
    return base64.b64encode(value).decode("ascii")
