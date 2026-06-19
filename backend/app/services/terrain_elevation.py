"""Sample ground elevation from public Terrarium DEM tiles."""

from __future__ import annotations

import logging
import math
import struct
import zlib
from pathlib import Path

import requests

from app.services.raster_cache import CACHE_ROOT

logger = logging.getLogger(__name__)

TERRARIUM_ZOOM = 12
TERRARIUM_TILE_SIZE = 256
TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TERRARIUM_CACHE_ROOT = CACHE_ROOT / "terrarium_dem"


def _latlon_to_tile_pixel(latitude: float, longitude: float, zoom: int) -> tuple[int, int, int, int]:
    lat = max(min(float(latitude), 85.05112878), -85.05112878)
    lon = ((float(longitude) + 180.0) % 360.0) - 180.0
    scale = 2**zoom
    x_float = (lon + 180.0) / 360.0 * scale
    sin_lat = math.sin(math.radians(lat))
    y_float = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    x_tile = int(min(max(math.floor(x_float), 0), scale - 1))
    y_tile = int(min(max(math.floor(y_float), 0), scale - 1))
    pixel_x = int(min(max(math.floor((x_float - x_tile) * TERRARIUM_TILE_SIZE), 0), TERRARIUM_TILE_SIZE - 1))
    pixel_y = int(min(max(math.floor((y_float - y_tile) * TERRARIUM_TILE_SIZE), 0), TERRARIUM_TILE_SIZE - 1))
    return x_tile, y_tile, pixel_x, pixel_y


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def _decode_png_rgba(png_bytes: bytes) -> tuple[int, int, bytes] | None:
    if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    width = height = color_type = bit_depth = None
    compressed = bytearray()
    while offset + 8 <= len(png_bytes):
        length = struct.unpack(">I", png_bytes[offset:offset + 4])[0]
        chunk_type = png_bytes[offset + 4:offset + 8]
        chunk_data = png_bytes[offset + 8:offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(">IIBBBBB", chunk_data)
            if bit_depth != 8 or color_type not in (2, 6) or interlace != 0:
                return None
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None or color_type is None:
        return None
    channels = 4 if color_type == 6 else 3
    stride = int(width) * channels
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error:
        return None
    rows = bytearray()
    previous = bytearray(stride)
    read_offset = 0
    for _row in range(int(height)):
        if read_offset >= len(raw):
            return None
        filter_type = raw[read_offset]
        read_offset += 1
        current = bytearray(raw[read_offset:read_offset + stride])
        read_offset += stride
        if len(current) != stride:
            return None
        for index in range(stride):
            left = current[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                current[index] = (current[index] + left) & 0xFF
            elif filter_type == 2:
                current[index] = (current[index] + up) & 0xFF
            elif filter_type == 3:
                current[index] = (current[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                current[index] = (current[index] + _paeth(left, up, upper_left)) & 0xFF
            elif filter_type != 0:
                return None
        rows.extend(current)
        previous = current
    return int(width), int(height), bytes(rows)


def _tile_path(zoom: int, x_tile: int, y_tile: int) -> Path:
    return TERRARIUM_CACHE_ROOT / str(zoom) / str(x_tile) / f"{y_tile}.png"


def _load_tile(zoom: int, x_tile: int, y_tile: int) -> bytes | None:
    path = _tile_path(zoom, x_tile, y_tile)
    if path.exists():
        try:
            return path.read_bytes()
        except OSError:
            logger.warning("Failed reading cached Terrarium tile %s", path, exc_info=True)
    url = TERRARIUM_URL.format(z=zoom, x=x_tile, y=y_tile)
    try:
        response = requests.get(url, timeout=8)
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("Failed fetching Terrarium tile %s", url, exc_info=True)
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    except OSError:
        logger.warning("Failed caching Terrarium tile %s", path, exc_info=True)
    return response.content


def sample_ground_elevation_m(latitude: float | None, longitude: float | None, *, zoom: int = TERRARIUM_ZOOM) -> float | None:
    if latitude is None or longitude is None or not math.isfinite(float(latitude)) or not math.isfinite(float(longitude)):
        return None
    if abs(float(latitude)) > 90 or abs(float(longitude)) > 180:
        return None
    x_tile, y_tile, pixel_x, pixel_y = _latlon_to_tile_pixel(float(latitude), float(longitude), zoom)
    png_bytes = _load_tile(zoom, x_tile, y_tile)
    if not png_bytes:
        return None
    decoded = _decode_png_rgba(png_bytes)
    if decoded is None:
        logger.warning("Failed decoding Terrarium tile z=%s x=%s y=%s", zoom, x_tile, y_tile)
        return None
    width, height, pixels = decoded
    channels = len(pixels) // (width * height)
    offset = (pixel_y * width + pixel_x) * channels
    red, green, blue = pixels[offset], pixels[offset + 1], pixels[offset + 2]
    return (red * 256.0 + green + blue / 256.0) - 32768.0
