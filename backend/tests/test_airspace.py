from app.services.airspace import parse_geojson_airspaces, parse_openair


def test_parse_openair_polygon_restricted_fields() -> None:
    payload = """AC DZ
AN DO NOT LAND - Sample Field
AL SFC
AH SFC
DP 29.07850074121879 N 82.0368666704882 W
DP 29.08041844762213 N 82.02447092495572 W
DP 29.09966082403472 N 82.02456480175168 W
DP 29.07850074121879 N 82.0368666704882 W
"""
    records = parse_openair(payload, kind="restricted_field")
    assert len(records) == 1
    assert records[0].is_restricted_field is True
    assert records[0].display_category == "RESTRICTED_FIELD"
    assert records[0].name == "DO NOT LAND - Sample Field"
    assert records[0].geometry_json["type"] == "Polygon"


def test_parse_openair_circle_airspace() -> None:
    payload = """AC C
AN Test Class C
AL SFC
AH FL100
V X=28.5000 N 81.5000 W
DC 5 NM
"""
    records = parse_openair(payload, kind="airspace")
    assert len(records) == 1
    assert records[0].display_category == "C"
    assert records[0].upper_limit_m is not None
    assert len(records[0].geometry_json["coordinates"][0]) > 10


def test_parse_geojson_airspace_polygons() -> None:
    payload = """{
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "properties": {
            "name": "Restricted Area",
            "class": "R",
            "lower_limit": "SFC",
            "upper_limit": "4500 ft"
          },
          "geometry": {
            "type": "Polygon",
            "coordinates": [[[-81.9, 28.3], [-81.8, 28.3], [-81.8, 28.4], [-81.9, 28.3]]]
          }
        }
      ]
    }"""
    records = parse_geojson_airspaces(payload, kind="airspace")
    assert len(records) == 1
    assert records[0].display_category == "R"
    assert records[0].lower_limit_m == 0
