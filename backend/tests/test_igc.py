from app.services.igc import parse_igc


def test_parse_igc_extracts_fixes() -> None:
    content = b"AXXX\nHFDTE170326\nHFPLTPILOTINCHARGE:Demo Pilot\nB1200003612345N11812345WA0123401234\nB1201003612445N11812445WA0123501235\n"
    parsed = parse_igc(content)
    assert parsed.metadata["pilot_name"] == "Demo Pilot"
    assert parsed.metadata["fix_count"] == 2
    assert parsed.fixes[0].latitude > 36


def test_parse_igc_supports_hfdtedate_and_rollover() -> None:
    content = (
        b"AXXX\n"
        b"HFDTEDATE:170326,01\n"
        b"B2359593612345N11812345WA0123401234\n"
        b"B0001003612445N11812445WA0000099999\n"
    )
    parsed = parse_igc(content)
    assert parsed.metadata["flight_date"] == "2026-03-17"
    assert parsed.metadata["flight_date_source"] == "HFDTEDATE"
    assert parsed.metadata["midnight_rollover_detected"] is True
    assert parsed.fixes[1].recorded_at.date().isoformat() == "2026-03-18"
    assert parsed.fixes[1].pressure_altitude_m is None
    assert parsed.fixes[1].gps_altitude_m is None


def test_parse_igc_deduplicates_identical_fixes() -> None:
    content = (
        b"AXXX\n"
        b"HFDTE170326\n"
        b"B1200003612345N11812345WA0123401234\n"
        b"B1200003612345N11812345WA0123401234\n"
        b"B1201003612445N11812445WA0123501235\n"
    )
    parsed = parse_igc(content)
    assert parsed.metadata["fix_count"] == 2
