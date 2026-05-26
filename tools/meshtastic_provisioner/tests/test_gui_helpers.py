from provisioner.gui import format_review_value, setting_label


def test_setting_label_names_identity_and_matrix_paths():
    assert setting_label("owner") == "Name"
    assert setting_label("owner_short") == "Shortname"
    assert setting_label("module_config.mqtt.address") == "Broker address"


def test_format_review_value_matches_operator_friendly_matrix_display():
    assert format_review_value("config.device.serial_enabled", True) == "Yes"
    assert format_review_value("config.device.serial_enabled", False) == "No"
    assert format_review_value("config.position.position_flags", 0x01 | 0x200) == "Altitude, Speed"
