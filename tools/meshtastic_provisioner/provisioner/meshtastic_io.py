"""Meshtastic serial discovery and provisioning adapter."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Any

from google.protobuf.json_format import MessageToDict
from serial.tools import list_ports

from .profiles import decode_psk, encode_psk, required_placeholders


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class SerialPortSummary:
    device: str
    description: str
    hwid: str
    serial_number: str | None = None
    vid: int | None = None
    pid: int | None = None


@dataclass(frozen=True)
class DeviceInfo:
    port: str
    usb_description: str
    usb_serial: str
    long_name: str
    short_name: str
    node_id: str
    firmware: str
    hardware: str
    region: str
    modem_preset: str
    mqtt_address: str
    mqtt_proxy: bool
    channel_psk: str
    uplink_enabled: bool
    downlink_enabled: bool
    status: str = "Ready"
    error: str = ""


def serial_ports() -> list[SerialPortSummary]:
    ports: list[SerialPortSummary] = []
    for port in list_ports.comports():
        ports.append(
            SerialPortSummary(
                device=port.device,
                description=port.description,
                hwid=port.hwid,
                serial_number=getattr(port, "serial_number", None),
                vid=getattr(port, "vid", None),
                pid=getattr(port, "pid", None),
            )
        )
    return ports


def scan_devices(log: LogCallback | None = None, ports: Iterable[SerialPortSummary] | None = None) -> list[DeviceInfo]:
    results: list[DeviceInfo] = []
    for port in ports or serial_ports():
        if log:
            log(f"Scanning {port.device}...")
        try:
            results.append(scan_port(port))
        except Exception as exc:
            if _looks_like_usb_serial(port):
                results.append(
                    DeviceInfo(
                        port=port.device,
                        usb_description=port.description,
                        usb_serial=port.serial_number or "",
                        long_name="",
                        short_name="",
                        node_id="",
                        firmware="",
                        hardware="",
                        region="",
                        modem_preset="",
                        mqtt_address="",
                        mqtt_proxy=False,
                        channel_psk="",
                        uplink_enabled=False,
                        downlink_enabled=False,
                        status="Error",
                        error=str(exc),
                    )
                )
            elif log:
                log(f"Skipping {port.device}: {exc}")
    return results


def _looks_like_usb_serial(port: SerialPortSummary) -> bool:
    text = f"{port.description} {port.hwid}".lower()
    return port.device.upper().startswith("COM") and ("usb" in text or port.vid is not None)


def scan_port(port: SerialPortSummary, timeout: int = 10) -> DeviceInfo:
    import meshtastic.serial_interface
    from meshtastic.protobuf import mesh_pb2

    interface = meshtastic.serial_interface.SerialInterface(devPath=port.device, noNodes=True, timeout=timeout)
    try:
        config = _message_dict(interface.localNode.localConfig)
        module_config = _message_dict(interface.localNode.moduleConfig)
        lora = config.get("lora", {})
        mqtt = module_config.get("mqtt", {})
        channel = _channel_summary(interface)
        node_num = _node_num(interface)
        metadata = getattr(interface, "metadata", None)
        hardware = ""
        if metadata is not None and getattr(metadata, "hw_model", None) is not None:
            try:
                hardware = mesh_pb2.HardwareModel.Name(metadata.hw_model)
            except Exception:
                hardware = str(metadata.hw_model)
        return DeviceInfo(
            port=port.device,
            usb_description=port.description,
            usb_serial=port.serial_number or "",
            long_name=interface.getLongName() or "",
            short_name=interface.getShortName() or "",
            node_id=f"!{node_num:08x}" if node_num else "",
            firmware=getattr(metadata, "firmware_version", "") if metadata else "",
            hardware=hardware,
            region=str(lora.get("region", "")),
            modem_preset=str(lora.get("modem_preset", "")),
            mqtt_address=str(mqtt.get("address", "")),
            mqtt_proxy=bool(mqtt.get("proxy_to_client_enabled") or mqtt.get("proxyToClientEnabled")),
            channel_psk=channel["psk"],
            uplink_enabled=channel["uplink_enabled"],
            downlink_enabled=channel["downlink_enabled"],
        )
    finally:
        interface.close()


def _message_dict(message: Any) -> dict[str, Any]:
    return MessageToDict(message, preserving_proto_field_name=True)


def _node_num(interface: Any) -> int:
    my_info = getattr(interface, "myInfo", None)
    if my_info is not None and hasattr(my_info, "my_node_num"):
        return int(my_info.my_node_num)
    info = interface.getMyNodeInfo() or {}
    return int(info.get("num", 0))


def _channel_summary(interface: Any) -> dict[str, Any]:
    channel = interface.localNode.channels[0]
    settings = channel.settings
    psk = bytes(settings.psk)
    return {
        "psk": encode_psk(psk),
        "uplink_enabled": bool(settings.uplink_enabled),
        "downlink_enabled": bool(settings.downlink_enabled),
    }


def backup_dir() -> Path:
    path = Path.home() / "Documents" / "Aervyx Meshtastic Provisioner" / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def apply_target(port: str, target: dict[str, Any], log: LogCallback | None = None) -> list[str]:
    missing = required_placeholders(target)
    if missing:
        raise ValueError("Missing required fleet settings: " + ", ".join(missing))

    import meshtastic
    import meshtastic.__main__ as cli
    import meshtastic.serial_interface
    from meshtastic.protobuf import channel_pb2

    def emit(message: str) -> None:
        if log:
            log(message)

    interface = meshtastic.serial_interface.SerialInterface(devPath=port, noNodes=True, timeout=15)
    backup_path: Path | None = None
    try:
        node = interface.localNode
        backup_path = backup_dir() / f"{port}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
        backup_path.write_text(cli.export_config(interface), encoding="utf-8")
        emit(f"{port}: backed up current config to {backup_path}")

        node.beginSettingsTransaction()
        if target.get("owner") or target.get("owner_short"):
            emit(f"{port}: writing owner")
            node.setOwner(target.get("owner"), target.get("owner_short"))
            time.sleep(0.5)

        for section, values in target.get("config", {}).items():
            emit(f"{port}: writing {section} config")
            cli.traverseConfig(section, values, node.localConfig)
            node.writeConfig(meshtastic.util.camel_to_snake(section))
            time.sleep(0.5)

        for section, values in target.get("module_config", {}).items():
            emit(f"{port}: writing {section} module")
            cli.traverseConfig(section, values, node.moduleConfig)
            node.writeConfig(meshtastic.util.camel_to_snake(section))
            time.sleep(0.5)

        primary = target.get("channel", {}).get("primary")
        if primary:
            emit(f"{port}: writing primary channel")
            channel = node.channels[0]
            channel.role = channel_pb2.Channel.Role.PRIMARY
            if "name" in primary:
                channel.settings.name = str(primary.get("name") or "")
            if "psk" in primary:
                channel.settings.psk = decode_psk(primary.get("psk"))
            if "uplink_enabled" in primary:
                channel.settings.uplink_enabled = bool(primary["uplink_enabled"])
            if "downlink_enabled" in primary:
                channel.settings.downlink_enabled = bool(primary["downlink_enabled"])
            node.writeChannel(0)
            time.sleep(0.5)

        emit(f"{port}: committing settings")
        node.commitSettingsTransaction()
    finally:
        interface.close()

    emit(f"{port}: waiting for reboot/reconnect")
    verified = wait_and_verify(port, target, log=log)
    if verified:
        emit(f"{port}: verified")
    return verified


def wait_and_verify(port: str, target: dict[str, Any], log: LogCallback | None = None, timeout_seconds: int = 90) -> list[str]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            findings = verify_target(port, target)
            if not findings:
                return []
            last_error = "; ".join(findings[:4])
        except Exception as exc:
            last_error = str(exc)
        time.sleep(5)
        if log:
            log(f"{port}: still waiting ({last_error})")
    raise TimeoutError(f"{port}: verification timed out: {last_error}")


def verify_target(port: str, target: dict[str, Any]) -> list[str]:
    import meshtastic.serial_interface

    findings: list[str] = []
    interface = meshtastic.serial_interface.SerialInterface(devPath=port, noNodes=True, timeout=15)
    try:
        if target.get("owner") and interface.getLongName() != target["owner"]:
            findings.append("owner mismatch")
        if target.get("owner_short") and interface.getShortName() != target["owner_short"]:
            findings.append("shortname mismatch")

        actual_config = _message_dict(interface.localNode.localConfig)
        actual_module = _message_dict(interface.localNode.moduleConfig)
        _compare_nested(target.get("config", {}), actual_config, "config", findings)
        _compare_nested(target.get("module_config", {}), actual_module, "module_config", findings)

        primary = target.get("channel", {}).get("primary")
        if primary:
            channel = _channel_summary(interface)
            if "psk" in primary and encode_psk(decode_psk(primary["psk"])) != channel["psk"]:
                findings.append("channel.primary.psk mismatch")
            if "uplink_enabled" in primary and bool(primary["uplink_enabled"]) != channel["uplink_enabled"]:
                findings.append("channel.primary.uplink_enabled mismatch")
            if "downlink_enabled" in primary and bool(primary["downlink_enabled"]) != channel["downlink_enabled"]:
                findings.append("channel.primary.downlink_enabled mismatch")
    finally:
        interface.close()
    return findings


def _compare_nested(expected: dict[str, Any], actual: dict[str, Any], path: str, findings: list[str]) -> None:
    for key, expected_value in expected.items():
        current_path = f"{path}.{key}"
        if isinstance(expected_value, dict):
            actual_value = actual.get(key, {})
            if not isinstance(actual_value, dict):
                findings.append(f"{current_path} missing")
            else:
                _compare_nested(expected_value, actual_value, current_path, findings)
        else:
            actual_value = actual.get(key)
            if str(actual_value) != str(expected_value):
                findings.append(f"{current_path} expected {expected_value!r} got {actual_value!r}")
