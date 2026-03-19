from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

B_RECORD_RE = re.compile(
    r"^B(?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})(?P<lat>\d{7})(?P<lat_hemi>[NS])(?P<lon>\d{8})(?P<lon_hemi>[EW])[AV](?P<pressure>\d{5})(?P<gps>\d{5})"
)
LEGACY_DATE_RE = re.compile(r"^HFDTE(?P<day>\d{2})(?P<month>\d{2})(?P<year>\d{2})")
MODERN_DATE_RE = re.compile(r"^HFDTEDATE:(?P<day>\d{2})(?P<month>\d{2})(?P<year>\d{2})(?:,\d+)?")


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


def _parse_header_date(line: str) -> tuple[date, str] | None:
    for source, pattern in (("HFDTE", LEGACY_DATE_RE), ("HFDTEDATE", MODERN_DATE_RE)):
        match = pattern.match(line)
        if match is None:
            continue
        year = 2000 + int(match.group("year"))
        parsed_date = date(year, int(match.group("month")), int(match.group("day")))
        return parsed_date, source
    return None


def _sanitize_altitude(raw_altitude: str) -> int | None:
    altitude = int(raw_altitude)
    if altitude in {0, 99999}:
        return None
    return altitude


def parse_igc(content: bytes) -> ParsedIGC:
    text = content.decode("utf-8", errors="ignore")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    metadata: dict[str, str | int | bool] = {}
    flight_date = date.today()
    metadata["flight_date_source"] = "fallback_today"
    metadata["flight_date"] = flight_date.isoformat()
    fixes: list[TrackFix] = []
    previous_clock_time: time | None = None
    date_offset_days = 0

    for line in lines:
        header_date = _parse_header_date(line)
        if header_date is not None:
            flight_date, source = header_date
            metadata["flight_date"] = flight_date.isoformat()
            metadata["flight_date_source"] = source
            continue
        if line.startswith("HFPLTPILOTINCHARGE:") or line.startswith("HFPLTPILOT:") or line.startswith("HOPLTPILOT:"):
            metadata["pilot_name"] = line.split(":", 1)[1].strip()
            continue
        match = B_RECORD_RE.match(line)
        if match is None:
            continue

        clock_time = time(int(match.group("hour")), int(match.group("minute")), int(match.group("second")))
        if previous_clock_time is not None and clock_time < previous_clock_time:
            date_offset_days += 1
            metadata["midnight_rollover_detected"] = True
        previous_clock_time = clock_time

        current_date = flight_date + timedelta(days=date_offset_days)
        fix = TrackFix(
            recorded_at=datetime.combine(current_date, clock_time, tzinfo=UTC),
            latitude=_decode_coordinate(match.group("lat"), match.group("lat_hemi"), 2),
            longitude=_decode_coordinate(match.group("lon"), match.group("lon_hemi"), 3),
            pressure_altitude_m=_sanitize_altitude(match.group("pressure")),
            gps_altitude_m=_sanitize_altitude(match.group("gps")),
        )
        if fixes:
            previous_fix = fixes[-1]
            if (
                fix.recorded_at == previous_fix.recorded_at
                and fix.latitude == previous_fix.latitude
                and fix.longitude == previous_fix.longitude
                and fix.pressure_altitude_m == previous_fix.pressure_altitude_m
                and fix.gps_altitude_m == previous_fix.gps_altitude_m
            ):
                continue
        fixes.append(fix)

    if not fixes:
        raise ValueError("No valid B records found in IGC upload.")

    metadata["fix_count"] = len(fixes)
    return ParsedIGC(metadata=metadata, fixes=fixes)
