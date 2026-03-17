from app.services.turnpoints import parse_csv_turnpoints, parse_geojson_turnpoints


def test_parse_csv_turnpoints() -> None:
    records = parse_csv_turnpoints("name,code,latitude,longitude\nLaunch,LCH,36.6,-118.0\n")
    assert len(records) == 1
    assert records[0].code == "LCH"


def test_parse_geojson_turnpoints() -> None:
    payload = '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"Goal"},"geometry":{"type":"Point","coordinates":[-118.3,36.8]}}]}'
    records = parse_geojson_turnpoints(payload)
    assert records[0].name == "Goal"