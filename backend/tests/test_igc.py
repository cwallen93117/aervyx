from app.services.igc import parse_igc


def test_parse_igc_extracts_fixes() -> None:
    content = b"AXXX\nHFDTE170326\nHFPLTPILOTINCHARGE:Demo Pilot\nB1200003612345N11812345WA0123401234\nB1201003612445N11812445WA0123501235\n"
    parsed = parse_igc(content)
    assert parsed.metadata["pilot_name"] == "Demo Pilot"
    assert parsed.metadata["fix_count"] == 2
    assert parsed.fixes[0].latitude > 36