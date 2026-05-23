from provisioner.meshtastic_io import SerialPortSummary, scan_devices


def test_scan_devices_uses_supplied_port_list_and_never_hardcodes_com_ports(monkeypatch):
    scanned = []

    def fake_scan_port(port):
        scanned.append(port.device)
        raise RuntimeError("not a meshtastic device")

    monkeypatch.setattr("provisioner.meshtastic_io.scan_port", fake_scan_port)
    ports = [
        SerialPortSummary(device="COM12", description="USB Serial Device", hwid="USB VID:PID=1234:5678", vid=1, pid=2),
        SerialPortSummary(device="COM42", description="USB Serial Device", hwid="USB VID:PID=1234:5678", vid=1, pid=2),
    ]
    results = scan_devices(ports=ports)
    assert scanned == ["COM12", "COM42"]
    assert [result.port for result in results] == ["COM12", "COM42"]
