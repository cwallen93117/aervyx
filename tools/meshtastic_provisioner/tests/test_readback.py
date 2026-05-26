from provisioner.meshtastic_io import compare_target_changes, evaluate_readback


def _snapshot(**overrides):
    base = {
        "owner": "Old Name",
        "owner_short": "OLD",
        "config": {
            "device": {"role": "CLIENT", "serial_enabled": True},
            "lora": {"hop_limit": 3},
        },
        "module_config": {
            "mqtt": {"enabled": True, "address": "mqtt-old.example", "proxy_to_client_enabled": True},
        },
        "channel": {
            "primary": {"name": "", "psk": "default", "uplink_enabled": True, "downlink_enabled": True},
        },
    }
    _deep_update(base, overrides)
    return base


def _deep_update(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def test_compare_target_changes_omits_unchanged_values():
    current = _snapshot()
    target = _snapshot()

    assert compare_target_changes(current, target) == []


def test_compare_target_changes_finds_identity_config_module_and_channel_changes():
    current = _snapshot()
    target = _snapshot(
        owner="New Name",
        owner_short="NEW",
        config={"device": {"role": "TRACKER"}},
        module_config={"mqtt": {"address": "mqtt-new.example"}},
        channel={"primary": {"name": "RaceNet", "psk": "none"}},
    )

    paths = {change.path for change in compare_target_changes(current, target)}

    assert paths == {
        "owner",
        "owner_short",
        "config.device.role",
        "module_config.mqtt.address",
        "channel.primary.name",
        "channel.primary.psk",
    }


def test_evaluate_readback_marks_matching_rows_ok_and_mismatches_error():
    current = _snapshot()
    target = _snapshot(
        owner="New Name",
        config={"device": {"role": "TRACKER"}},
        module_config={"mqtt": {"address": "mqtt-new.example"}},
    )
    comparisons = compare_target_changes(current, target)

    matching = evaluate_readback(comparisons, target)
    assert {result.path: result.ok for result in matching} == {
        "owner": True,
        "config.device.role": True,
        "module_config.mqtt.address": True,
    }

    failed_actual = _snapshot(
        owner="New Name",
        config={"device": {"role": "CLIENT"}},
        module_config={"mqtt": {"address": "mqtt-new.example"}},
    )
    failed = evaluate_readback(comparisons, failed_actual)

    assert {result.path: result.ok for result in failed} == {
        "owner": True,
        "config.device.role": False,
        "module_config.mqtt.address": True,
    }
    assert [result.error for result in failed if result.path == "config.device.role"] == ["got 'CLIENT'"]
