from provisioner.profiles import build_target_config, decode_psk, display_value, load_profile_bundle, profile_settings, required_placeholders, save_profile_bundle
from provisioner.schema import MATRIX_ROWS, PROFILE_KEYS, format_position_flags, get_path


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


def test_profile_matrix_shows_mqtt_password_values():
    bundle = load_profile_bundle()
    bundle["profiles"]["pilot"]["settings"]["module_config"]["mqtt"]["password"] = "visible-password"

    assert display_value(bundle, "pilot", "module_config.mqtt.password", secret=True) == "visible-password"


def test_save_profile_bundle_persists_editable_matrix_values(monkeypatch, tmp_path):
    overlay = tmp_path / "aervyx_profiles.local.yaml"
    monkeypatch.setenv("AERVYX_PROVISIONER_PROFILE", str(overlay))
    bundle = load_profile_bundle()
    bundle["profiles"]["pilot"]["settings"]["module_config"]["mqtt"]["username"] = "fleet-user"
    bundle["profiles"]["pilot"]["settings"]["module_config"]["mqtt"]["password"] = "fleet-password"

    saved_path = save_profile_bundle(bundle)
    reloaded = load_profile_bundle()

    assert saved_path == overlay
    assert reloaded["profiles"]["pilot"]["settings"]["module_config"]["mqtt"]["username"] == "fleet-user"
    assert reloaded["profiles"]["pilot"]["settings"]["module_config"]["mqtt"]["password"] == "fleet-password"


def test_wired_base_station_profile_enables_ethernet_not_wifi():
    bundle = load_profile_bundle()
    network = bundle["profiles"]["wired_base_station"]["settings"]["config"]["network"]

    assert network["eth_enabled"] is True
    assert network["wifi_enabled"] is False


def test_position_flags_are_displayed_as_named_fields():
    assert format_position_flags(0x01 | 0x80 | 0x200) == "Altitude, Timestamp, Speed"
