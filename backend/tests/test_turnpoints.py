from app.services.turnpoints import parse_csv_turnpoints, parse_geojson_turnpoints, parse_gpx_turnpoints


def test_parse_csv_turnpoints() -> None:
    records = parse_csv_turnpoints("name,code,latitude,longitude\nLaunch,LCH,36.6,-118.0\n")
    assert len(records) == 1
    assert records[0].code == "LCH"


def test_parse_geojson_turnpoints() -> None:
    payload = '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"Goal"},"geometry":{"type":"Point","coordinates":[-118.3,36.8]}}]}'
    records = parse_geojson_turnpoints(payload)
    assert records[0].name == "Goal"


def test_parse_gpx_turnpoints() -> None:
    payload = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="FlightComp">
  <wpt lat="36.606" lon="-118.062">
    <name>Launch Ridge</name>
    <sym>LCH</sym>
    <ele>1900</ele>
  </wpt>
  <wpt lat="36.810" lon="-118.320">
    <name>Goal Field</name>
    <type>GL1</type>
  </wpt>
</gpx>
"""
    records = parse_gpx_turnpoints(payload)
    assert len(records) == 2
    assert records[0].name == "Launch Ridge"
    assert records[0].code == "LCH"
    assert records[0].elevation_m == 1900
    assert records[1].code == "GL1"


def test_parse_gpx_ignores_url_symbol_codes() -> None:
    payload = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="FlightComp">
  <wpt lat="38.692468708" lon="-75.071779914">
    <ele>2.5</ele>
    <name>dewey</name>
    <sym>http://maps.google.com/mapfiles/kml/shapes/flag.png</sym>
  </wpt>
</gpx>
"""
    records = parse_gpx_turnpoints(payload)
    assert len(records) == 1
    assert records[0].name == "dewey"
    assert records[0].code is None
