from __future__ import annotations

from copy import deepcopy
from typing import Any

MAP_OVERLAY_CONTEXTS = [
    "task_builder",
    "scoring",
    "logbook_replay",
    "dashboard_live",
    "public_live",
    "airspace_explorer",
    "soaring_forecast",
    "admin_site_preview",
]

MAP_OVERLAY_GROUPS = [
    "tasks",
    "airspace",
    "flight_tracks",
    "live_tracking",
    "replay",
    "weather",
    "map_controls",
    "site_preview",
]

LEGACY_MAP_OVERLAY_DEFAULTS: dict[str, dict[str, bool]] = {
    "task_builder": {
        "turnpoints": True, "task_route": True, "task_cylinders": True,
        "optimized_route": True, "leg_labels": True, "airspaces": True,
        "airspace_labels": True, "faa_airspace": True, "flight_track": True, "distance_summary": True,
        "fullscreen_toggle": True, "2d_3d_toggle": True, "basemap_selector": True,
        "altitude_slider": True, "click_to_add_turnpoint": True, "fullscreen_editor_panel": True,
    },
    "scoring": {
        "turnpoints": True, "task_route": True, "task_cylinders": True,
        "optimized_route": True, "leg_labels": True, "airspaces": False,
        "airspace_labels": False, "faa_airspace": False, "flight_track": True, "track_highlight": True,
        "distance_summary": True, "fullscreen_toggle": True, "2d_3d_toggle": True,
        "basemap_selector": True, "altitude_slider": True, "fullscreen_editor_panel": True,
    },
    "logbook_replay": {
        "flight_track": True, "track_highlight": True, "replay_scrubber": True,
        "replay_speed": True, "fullscreen_toggle": True, "2d_3d_toggle": True,
        "basemap_selector": True, "altitude_slider": True,
    },
    "dashboard_live": {
        "turnpoints": True, "task_route": True, "task_cylinders": True,
        "airspaces": True, "airspace_labels": True, "faa_airspace": True, "flight_track": True,
        "live_positions": True, "live_labels": True, "fullscreen_toggle": True,
        "2d_3d_toggle": True, "basemap_selector": True, "altitude_slider": True,
    },
    "public_live": {
        "turnpoints": True, "task_route": True, "task_cylinders": True,
        "faa_airspace": True, "flight_track": True, "live_positions": True, "live_labels": True,
        "gps_button": True, "fullscreen_toggle": True, "2d_3d_toggle": True,
        "basemap_selector": True, "altitude_slider": True,
    },
    "airspace_explorer": {
        "airspace_regions": True, "airspace_labels": True, "tfrs": True,
        "tfr_labels": True, "category_toggles": True, "export_openair": True,
        "2d_3d_toggle": True, "legend": True,
    },
    "soaring_forecast": {
        "weather_raster": True, "wind_barbs": True, "sounding_popup": True,
        "model_selector": True, "overlay_tabs": True, "wind_barb_toggle": True,
        "opacity_slider": True, "time_scrubber": True, "model_run_selector": True,
        "legend": True,
    },
    "admin_site_preview": {
        "turnpoints": True, "fullscreen_toggle": True, "2d_3d_toggle": True,
        "basemap_selector": True, "altitude_slider": True,
    },
}

MAP_OVERLAY_GROUP_FEATURES: dict[str, dict[str, list[str]]] = {
    "task_builder": {
        "tasks": [
            "turnpoints", "task_route", "task_cylinders", "optimized_route",
            "leg_labels", "distance_summary", "click_to_add_turnpoint",
            "fullscreen_editor_panel",
        ],
        "airspace": ["airspaces", "airspace_labels", "faa_airspace"],
        "flight_tracks": ["flight_track"],
        "map_controls": ["fullscreen_toggle", "2d_3d_toggle", "basemap_selector", "altitude_slider"],
    },
    "scoring": {
        "tasks": [
            "turnpoints", "task_route", "task_cylinders", "optimized_route",
            "leg_labels", "distance_summary", "fullscreen_editor_panel",
        ],
        "airspace": ["airspaces", "airspace_labels", "faa_airspace"],
        "flight_tracks": ["flight_track", "track_highlight"],
        "map_controls": ["fullscreen_toggle", "2d_3d_toggle", "basemap_selector", "altitude_slider"],
    },
    "logbook_replay": {
        "flight_tracks": ["flight_track", "track_highlight"],
        "replay": ["replay_scrubber", "replay_speed"],
        "map_controls": ["fullscreen_toggle", "2d_3d_toggle", "basemap_selector", "altitude_slider"],
    },
    "dashboard_live": {
        "tasks": ["turnpoints", "task_route", "task_cylinders"],
        "airspace": ["airspaces", "airspace_labels", "faa_airspace"],
        "flight_tracks": ["flight_track"],
        "live_tracking": ["live_positions", "live_labels"],
        "map_controls": ["fullscreen_toggle", "2d_3d_toggle", "basemap_selector", "altitude_slider"],
    },
    "public_live": {
        "tasks": ["turnpoints", "task_route", "task_cylinders"],
        "airspace": ["faa_airspace"],
        "flight_tracks": ["flight_track"],
        "live_tracking": ["live_positions", "live_labels"],
        "map_controls": ["gps_button", "fullscreen_toggle", "2d_3d_toggle", "basemap_selector", "altitude_slider"],
    },
    "airspace_explorer": {
        "airspace": [
            "airspace_regions", "airspace_labels", "tfrs", "tfr_labels",
            "category_toggles", "export_openair", "legend",
        ],
        "map_controls": ["2d_3d_toggle"],
    },
    "soaring_forecast": {
        "weather": [
            "weather_raster", "wind_barbs", "sounding_popup", "model_selector",
            "overlay_tabs", "wind_barb_toggle", "opacity_slider", "time_scrubber",
            "model_run_selector", "legend",
        ],
    },
    "admin_site_preview": {
        "site_preview": ["turnpoints"],
        "map_controls": ["fullscreen_toggle", "2d_3d_toggle", "basemap_selector", "altitude_slider"],
    },
}


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _legacy_group_enabled(context: str, group: str, legacy_context: dict[str, Any]) -> bool:
    features = MAP_OVERLAY_GROUP_FEATURES[context][group]
    if any(feature in legacy_context for feature in features):
        return any(_coerce_bool(legacy_context.get(feature), False) for feature in features)
    return DEFAULT_MAP_OVERLAY_GROUPS[context][group]


def _build_default_groups() -> dict[str, dict[str, bool]]:
    groups: dict[str, dict[str, bool]] = {}
    for context in MAP_OVERLAY_CONTEXTS:
        context_groups: dict[str, bool] = {}
        legacy_context = LEGACY_MAP_OVERLAY_DEFAULTS[context]
        for group, features in MAP_OVERLAY_GROUP_FEATURES[context].items():
            context_groups[group] = any(legacy_context.get(feature) is True for feature in features)
        groups[context] = context_groups
    return groups


DEFAULT_MAP_OVERLAY_GROUPS = _build_default_groups()


def _expand_legacy_context(context: str, context_groups: dict[str, bool]) -> dict[str, bool]:
    legacy = deepcopy(LEGACY_MAP_OVERLAY_DEFAULTS[context])
    for group, features in MAP_OVERLAY_GROUP_FEATURES[context].items():
        if group in context_groups:
            enabled = context_groups[group]
            for feature in features:
                legacy[feature] = enabled
    return legacy


def expand_grouped_map_overlay_config(groups: dict[str, dict[str, bool]]) -> dict[str, Any]:
    config: dict[str, Any] = {
        "schema_version": 2,
        "groups": deepcopy(groups),
    }
    for context in MAP_OVERLAY_CONTEXTS:
        config[context] = _expand_legacy_context(context, groups[context])
    return config


def normalize_map_overlay_config(raw_config: Any) -> dict[str, Any]:
    raw = raw_config if isinstance(raw_config, dict) else {}
    raw_groups = raw.get("groups") if isinstance(raw.get("groups"), dict) else {}
    normalized_groups: dict[str, dict[str, bool]] = {}

    for context in MAP_OVERLAY_CONTEXTS:
        raw_context_groups = raw_groups.get(context) if isinstance(raw_groups.get(context), dict) else {}
        legacy_context = raw.get(context) if isinstance(raw.get(context), dict) else {}
        default_context_groups = DEFAULT_MAP_OVERLAY_GROUPS[context]
        context_groups: dict[str, bool] = {}

        for group in MAP_OVERLAY_GROUPS:
            if group not in MAP_OVERLAY_GROUP_FEATURES[context]:
                continue
            default_value = default_context_groups[group]
            if group in raw_context_groups:
                context_groups[group] = _coerce_bool(raw_context_groups.get(group), default_value)
            else:
                context_groups[group] = _legacy_group_enabled(context, group, legacy_context)

        normalized_groups[context] = context_groups

    return expand_grouped_map_overlay_config(normalized_groups)


DEFAULT_MAP_OVERLAY_CONFIG = normalize_map_overlay_config({})
