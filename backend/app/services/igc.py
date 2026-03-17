from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

B_RECORD_RE = re.compile(
    r"^B(?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})(?P<lat>\d{7})(?P<lat_hemi>[NS])(?P<lon>\d{8})(?P<lon_hemi>[EW])[AV](?P<pressure>\d{5})(?P<gps>\d{5})"
)
DATE_RE = re.compile(r"^HFDTE(?P<day>\d{2})(?P<month>\d{2})(?P<year>\d{2})")


@dataclass
class TrackFix:
    recorded_at: datetime
    latitude: float
    longitude: float
    pressure_altitude_m: int | None
    gps_altitude_m: int | None


@dataclass
class ParsedIGC:
    metadata: dict
    fixes: list[TrackFix]


def _decode_coordinate(raw: str, hemisphere: str, degree_digits: int) -> float:
    degrees = int(raw[:degree_digits])
    minutes = float(raw[degree_digits:]) / 1000.0
    coordinate = degrees + minutes / 60.0
    if hemisphere in {"S", "W"}:
        coordinate *= -1
    return coordinate


def parse_igc(content: bytes) -> ParsedIGC:
    text = content.decode("utf-8", errors="ignore")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    metadata: dict[str, str] = {}
    flight_date = date.today()
    fixes: list[TrackFix] = []

    for line in lines:
        date_match = DATE_RE.match(line)
        if date_match:
            year = 2000 + int(date_match.group("year"))
            flight_date = date(year, int(date_match.group("month")), int(date_match.group("day")))
            metadata["flight_date"] = flight_date.isoformat()
            continue
        if line.startswith("HFPLTPILOTINCHARGE:"):
            metadata["pilot_name"] = line.split(":", 1)[1].strip()
            continue
        match = B_RECORD_RE.match(line)
        if match is None:
            continue
        latitude = _decode_coordinate(match.group("lat"), match.group("lat_hemi"), 2)
        longitude = _decode_coordinate(match.group("lon"), match.group("lon_hemi"), 3)
        fixes.append(
            TrackFix(
                recorded_at=datetime.combine(
                    flight_date,
                    time(int(match.group("hour")), int(match.group("minute")), int(match.group("second"))),
                    tzinfo=UTC,
                ),
                latitude=latitude,
                longitude=longitude,
                pressure_altitude_m=int(match.group("pressure")),
                gps_altitude_m=int(match.group("gps")),
            )
        )

    if not fixes:
        raise ValueError("No valid B records found in IGC upload.")

    metadata["fix_count"] = len(fixes)
    return ParsedIGC(metadata=metadata, fixes=fixes)