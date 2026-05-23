from provisioner.profiles import build_target_config, decode_psk, load_profile_bundle, profile_settings, required_placeholders
from provisioner.schema import MATRIX_ROWS, PROFILE_KEYS, get_path


def test_bundled_profiles_cover_matrix_paths():
    bundle = load_profile_bundle()
    for profile in PROFILE_KEYS:
        settings = profile_settings(bundle, profile)
        for row in MATRIX_ROWS:
            assert get_path(settings, row.path, None) is not None, f"{profile} missing {row.path}"


def test_only_identity_is_required_when_overlay_supplies_secrets():
    bundle = load_profile_bundle()
    for profile in PROFILE_KEYS:
        settings = bundle["profiles"][profile]["settings"]
        settings["module_config"]["mqtt"]["username"] = "user"
        settings["module_config"]["mqtt"]["password"] = "pass"
        if settings["config"]["network"].get("wifi_enabled"):
            settings["config"]["network"]["wifi_ssid"] = "ssid"
            settings["config"]["network"]["wifi_psk"] = "password123"

    target = build_target_config(bundle, "pilot", "Pilot One", "P1")
    assert target["owner"] == "Pilot One"
    assert target["owner_short"] == "P1"
    assert required_placeholders(target) == []


def test_placeholders_block_apply_until_local_overlay_is_injected():
    bundle = load_profile_bundle()
    target = build_target_config(bundle, "pilot", "Pilot One", "P1")
    assert "module_config.mqtt.username" in required_placeholders(target)
    assert "module_config.mqtt.password" in required_placeholders(target)


def test_psk_default_decodes_to_meshtastic_default_key():
    assert decode_psk("default") == b"\x01"
    assert decode_psk("AQ==") == b"\x01"
