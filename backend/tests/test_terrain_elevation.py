import struct
import zlib

from app.services import terrain_elevation


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + b"\x00\x00\x00\x00"


def _terrarium_png(red: int, green: int, blue: int) -> bytes:
    width = height = 256
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = bytes([0]) + bytes([red, green, blue]) * width
    raw = row * height
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(raw)) + _png_chunk(b"IEND", b"")


def test_sample_ground_elevation_decodes_terrarium_tile(monkeypatch) -> None:
    # Terrarium: red * 256 + green + blue / 256 - 32768.
    # 128, 100, 0 -> 100 m.
    monkeypatch.setattr(terrain_elevation, "_load_tile", lambda zoom, x, y: _terrarium_png(128, 100, 0))

    elevation = terrain_elevation.sample_ground_elevation_m(36.0, -80.0)

    assert elevation == 100
