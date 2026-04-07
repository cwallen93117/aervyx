from __future__ import annotations

import asyncio
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/weather", tags=["weather"])

# Thread pool for synchronous Herbie calls
_executor = ThreadPoolExecutor(max_workers=2)

# GeoJSON result cache: key -> (json_dict, timestamp)
_grid_cache: dict[str, tuple[dict, float]] = {}
GRID_TTL = 900  # 15 min

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
MODEL_CONFIG: dict[str, dict[str, Any]] = {
    "gfs": {
        "label": "GFS",
        "resolution": "25km",
        "coverage": "Global",
        "herbie_model": "gfs",
        "default_product": "pgrb2.0p25",
        "run_hours": [0, 6, 12, 18],
        "max_fxx": 120,
        "fxx_step": 3,
    },
    "nam3km": {
        "label": "NAM 3km",
        "resolution": "3km",
        "coverage": "CONUS",
        "herbie_model": "nam",
        "default_product": "conusnest.hiresf",
        "run_hours": [0, 6, 12, 18],
        "max_fxx": 60,
        "fxx_step": 1,
    },
    "nam": {
        "label": "NAM",
        "resolution": "12km",
        "coverage": "N. America",
        "herbie_model": "nam",
        "default_product": "awip12",
        "run_hours": [0, 6, 12, 18],
        "max_fxx": 60,
        "fxx_step": 1,
    },
    "rap": {
        "label": "RAP",
        "resolution": "13km",
        "coverage": "N. America",
        "herbie_model": "rap",
        "default_product": None,
        "run_hours": list(range(24)),
        "max_fxx": 21,
        "fxx_step": 1,
    },
    "hrrr": {
        "label": "HRRR",
        "resolution": "3km",
        "coverage": "CONUS",
        "herbie_model": "hrrr",
        "default_product": "sfc",
        "run_hours": list(range(24)),
        "max_fxx": 18,
        "fxx_step": 1,
    },
    "nbm": {
        "label": "NBM",
        "resolution": "2.5km",
        "coverage": "CONUS",
        "herbie_model": "nbm",
        "default_product": "co",
        "run_hours": list(range(24)),
        "max_fxx": 36,
        "fxx_step": 1,
    },
}

# ---------------------------------------------------------------------------
# Variable definitions
# search: Herbie GRIB inventory regex
# product_overrides: model -> product when different from default_product
# is_wind_speed: if True, fetch both UGRD+VGRD and compute speed
# ---------------------------------------------------------------------------
VARIABLES: dict[str, dict[str, Any]] = {
    "cape": {
        "search": ":CAPE:surface:",
        "product_overrides": {},
    },
    "boundary_layer_height": {
        "search": ":HPBL:surface:",
        "product_overrides": {},
        "exclude_models": ["nbm"],
    },
    "lifted_index": {
        "search": ":4LFTX:",
        "product_overrides": {},
        "exclude_models": ["nbm"],
    },
    "cloud_cover": {
        "search": ":TCDC:entire atmosphere:",
        "product_overrides": {},
        "exclude_models": ["nbm"],
    },
    "precipitation": {
        "search": ":APCP:surface:",
        "product_overrides": {},
    },
    "vertical_velocity_700hPa": {
        "search": ":VVEL:700 mb:",
        "product_overrides": {"hrrr": "prs"},
        "exclude_models": ["nbm"],
    },
    # Derived updraft velocity — convective velocity scale W*
    # Uses SHTFL + BLH + T2m + Td2m + cloud cover for full derivation
    # Falls back to CAPE+BLH if SHTFL unavailable (e.g. fh=0)
    "thermal_updraft": {
        "search": ":SHTFL:surface:",
        "search_blh": ":HPBL:surface:",
        "search_cape": ":CAPE:surface:",
        "search_t2m": ":TMP:2 m above ground:",
        "search_td2m": ":DPT:2 m above ground:",
        "search_tcdc": ":TCDC:entire atmosphere:",
        "product_overrides": {},
        "exclude_models": ["nbm"],
        "derived": "shtfl_blh_updraft",
    },
    # Composite soaring quality index (0–10 scale)
    # Blends thermal strength, BL height, cloud cover, and surface wind
    "soaring_quality": {
        "search": ":SHTFL:surface:",
        "search_blh": ":HPBL:surface:",
        "search_cape": ":CAPE:surface:",
        "search_t2m": ":TMP:2 m above ground:",
        "search_td2m": ":DPT:2 m above ground:",
        "search_tcdc": ":TCDC:entire atmosphere:",
        "search_wind_u": ":UGRD:10 m above ground:",
        "search_wind_v": ":VGRD:10 m above ground:",
        "product_overrides": {},
        "exclude_models": ["nbm"],
        "derived": "soaring_composite",
    },
    # Buoyancy-to-shear ratio (B:S) — W* / wind shear across BL
    # Higher = thermals dominate over shear → better organized lift
    # Thresholds: <3 poor, 3-7 moderate, >7 good
    "bsratio": {
        "search": ":SHTFL:surface:",
        "search_blh": ":HPBL:surface:",
        "search_t2m": ":TMP:2 m above ground:",
        "search_td2m": ":DPT:2 m above ground:",
        "search_tcdc": ":TCDC:entire atmosphere:",
        "search_wind_u": ":UGRD:10 m above ground:",
        "search_wind_v": ":VGRD:10 m above ground:",
        "search_wind_bl_u": ":UGRD:850 mb:",
        "search_wind_bl_v": ":VGRD:850 mb:",
        "product_overrides": {"hrrr": "sfc"},
        "exclude_models": ["nbm"],
    },
    "convective_cloud_top": {
        "search": ":HGT:cloud top:",
        "product_overrides": {"hrrr": "prs"},
        "exclude_models": ["nbm"],
    },
    "convective_cloud_base": {
        "search": ":HGT:cloud base:",
        "product_overrides": {"hrrr": "prs"},
        "exclude_models": ["nbm"],
    },
    "wind_speed_10m": {
        "search": ":UGRD:10 m above ground:",
        "search_v": ":VGRD:10 m above ground:",
        "is_wind_speed": True,
        "product_overrides": {},
        "exclude_models": ["nbm"],
    },
    "wind_speed_850hPa": {
        "search": ":UGRD:850 mb:",
        "search_v": ":VGRD:850 mb:",
        "is_wind_speed": True,
        "product_overrides": {"hrrr": "prs"},
        "exclude_models": ["nbm"],
    },
    "wind_speed_700hPa": {
        "search": ":UGRD:700 mb:",
        "search_v": ":VGRD:700 mb:",
        "is_wind_speed": True,
        "product_overrides": {"hrrr": "prs"},
        "exclude_models": ["nbm"],
    },
    "wind_speed_500hPa": {
        "search": ":UGRD:500 mb:",
        "search_v": ":VGRD:500 mb:",
        "is_wind_speed": True,
        "product_overrides": {"hrrr": "prs"},
        "exclude_models": ["nbm"],
    },
}

# Subsample step per model to keep GeoJSON ~2000-5000 points
SUBSAMPLE: dict[str, int] = {
    "gfs": 10,
    "nam3km": 20,
    "nam": 12,
    "rap": 8,
    "hrrr": 20,
    "nbm": 15,
}

# Subsample steps for raster image — use full native resolution
RASTER_SUBSAMPLE: dict[str, int] = {
    "gfs": 1,       # 25km native
    "nam3km": 1,     # 3km native
    "nam": 1,        # 12km native
    "rap": 1,        # 13km native
    "hrrr": 1,       # 3km native
    "nbm": 1,        # 2.5km native
}

# Persistent raster cache (filesystem PNGs + SQLite metadata)
from app.services.raster_cache import get_cached_raster, store_raster

# ---------------------------------------------------------------------------
# Color ramp definitions for soaring weather visualization
# Each entry: list of (fraction, R, G, B, A) where fraction is 0.0-1.0.
# The actual value range is computed dynamically from data percentiles,
# so the ramp only defines the *shape* of the color progression.
# ---------------------------------------------------------------------------
# Ramp: position fraction (0-1) → (R, G, B, A)
_COLOR_RAMPS: dict[str, list[tuple[float, int, int, int, int]]] = {
    # thermal / updraft: XC Skies 9-stop ramp (0–1200 fpm / 0–6 m/s)
    "thermal": [
        (0.0,    200, 220, 255, 80),   # 0 fpm    — very light blue, nearly transparent
        (0.0833, 130, 180, 240, 160),  # 100 fpm  — light blue
        (0.1667, 60,  160, 220, 180),  # 200 fpm  — blue-teal
        (0.25,   40,  180, 140, 195),  # 300 fpm  — teal-green
        (0.3333, 80,  190, 60,  210),  # 400 fpm  — green
        (0.4167, 180, 210, 40,  220),  # 500 fpm  — yellow-green
        (0.5833, 240, 190, 30,  230),  # 700 fpm  — yellow-orange
        (0.75,   230, 110, 20,  240),  # 900 fpm  — orange-red
        (1.0,    210, 30,  30,  245),  # 1200 fpm — red
    ],
    # instability: red(unstable)→orange→yellow→green→blue(stable)
    "instability": [
        (0.0,  220, 30,  20,  230),
        (0.25, 220, 140, 20,  215),
        (0.45, 210, 210, 40,  200),
        (0.6,  70,  200, 70,  190),
        (0.8,  40,  140, 220, 170),
        (1.0,  40,  60,  180, 155),
    ],
    # height: 21-stop XC-Skies-style altitude ramp  0–6096 m (0–20 000 ft)
    "height": [
        (0.0,   100, 90,  120, 170),   #     0 ft — dark gray-purple
        (0.05,  120, 100, 155, 180),   #  1000 ft — medium purple
        (0.10,  160, 140, 190, 185),   #  2000 ft — lavender
        (0.15,  130, 120, 200, 190),   #  3000 ft — blue-violet
        (0.20,  80,  110, 200, 195),   #  4000 ft — medium blue
        (0.25,  90,  150, 210, 200),   #  5000 ft — sky blue
        (0.30,  100, 185, 220, 200),   #  6000 ft — light blue
        (0.35,  60,  180, 180, 200),   #  7000 ft — teal
        (0.40,  60,  185, 140, 205),   #  8000 ft — green-teal
        (0.45,  70,  180, 90,  210),   #  9000 ft — medium green
        (0.50,  100, 200, 60,  215),   # 10000 ft — bright green
        (0.55,  160, 210, 50,  220),   # 11000 ft — yellow-green
        (0.60,  210, 210, 50,  220),   # 12000 ft — yellow
        (0.65,  220, 200, 70,  220),   # 13000 ft — light gold
        (0.70,  225, 180, 50,  220),   # 14000 ft — gold/amber
        (0.75,  230, 170, 100, 215),   # 15000 ft — light orange
        (0.80,  220, 150, 120, 210),   # 16000 ft — salmon
        (0.85,  215, 160, 160, 200),   # 17000 ft — light pink
        (0.90,  200, 195, 195, 190),   # 18000 ft — light gray
        (0.95,  215, 210, 210, 180),   # 19000 ft — very light gray
        (1.0,   240, 240, 230, 150),   # 20000 ft — near white
    ],
    # cloud: clear→gray→dark
    "cloud": [
        (0.0,  230, 230, 230, 50),
        (0.2,  200, 205, 210, 130),
        (0.5,  150, 155, 160, 175),
        (0.8,  80,  85,  90,  215),
        (1.0,  35,  40,  45,  235),
    ],
    # precipitation: light blue→blue→indigo→purple
    "precip": [
        (0.0,  160, 210, 240, 70),
        (0.15, 80,  160, 230, 160),
        (0.4,  40,  90,  210, 200),
        (0.7,  110, 40,  190, 220),
        (1.0,  140, 20,  160, 235),
    ],
    # wind: green→yellow→orange→red
    "wind": [
        (0.0,  50,  180, 80,  150),
        (0.2,  80,  210, 70,  180),
        (0.4,  200, 220, 40,  200),
        (0.65, 220, 140, 30,  220),
        (0.85, 220, 60,  20,  230),
        (1.0,  200, 20,  20,  235),
    ],
    # bsratio: red(shear-dominated)→orange→yellow→green→teal→blue(buoyancy-dominated)
    "bsratio": [
        (0.0,   220, 60,  60,  180),  # 0  — red (shear-dominated)
        (0.15,  230, 140, 40,  200),  # 3  — orange
        (0.25,  220, 200, 40,  210),  # 5  — yellow
        (0.35,  120, 200, 60,  220),  # 7  — green
        (0.5,   60,  180, 140, 230),  # 10 — teal
        (1.0,   40,  120, 200, 240),  # 20 — blue (buoyancy-dominated)
    ],
    # soaring quality: red(bad)→orange→yellow→green→blue(great)
    "soaring": [
        (0.0,  180, 180, 180, 100),  # gray — no soaring
        (0.15, 200, 100, 80,  160),  # dull red
        (0.3,  220, 160, 40,  190),  # orange
        (0.5,  210, 210, 50,  210),  # yellow
        (0.7,  100, 200, 80,  225),  # green
        (0.85, 50,  170, 220, 235),  # blue
        (1.0,  30,  80,  200, 245),  # deep blue — epic day
    ],
}

# Fixed scale config per variable — NO adaptive scaling.
# Same colors every day for easy visual comparison across forecasts.
#   ramp:       color ramp name
#   scale_min:  hard floor for color scale
#   scale_max:  hard ceiling for color scale
#   clamp_neg:  if True, clamp data values < 0 to 0 before color mapping
_VAR_SCALE: dict[str, dict] = {
    # Raw omega (700 hPa) — kept for reference but not primary overlay
    "vertical_velocity_700hPa": {
        "ramp": "thermal", "scale_min": 0.0, "scale_max": 1.5, "clamp_neg": True,
    },
    # Derived thermal updraft: 0 to 6 m/s (~1200 fpm)
    # W* from SHTFL+BLH with moisture/cloud corrections
    "thermal_updraft": {
        "ramp": "thermal", "scale_min": 0.0, "scale_max": 6.096, "clamp_neg": True,
    },
    # Composite soaring quality: 0 to 10
    "soaring_quality": {
        "ramp": "soaring", "scale_min": 0.0, "scale_max": 10.0, "clamp_neg": True,
    },
    # Buoyancy-to-shear ratio: 0 to 20 (dimensionless)
    "bsratio": {
        "ramp": "bsratio", "scale_min": 0.0, "scale_max": 20.0, "clamp_neg": True,
    },
    # CAPE: 0 to 4000 J/kg
    "cape": {
        "ramp": "thermal", "scale_min": 0.0, "scale_max": 4000.0, "clamp_neg": True,
    },
    # Cloud top height: 0 to 6096 m (0–20 000 ft)
    "convective_cloud_top": {
        "ramp": "height", "scale_min": 0.0, "scale_max": 6096.0, "clamp_neg": True,
    },
    # Cloud base height: 0 to 6096 m (0–20 000 ft)
    "convective_cloud_base": {
        "ramp": "height", "scale_min": 0.0, "scale_max": 6096.0, "clamp_neg": True,
    },
    # Boundary layer height: 0 to 6096 m (0–20 000 ft)
    "boundary_layer_height": {
        "ramp": "height", "scale_min": 0.0, "scale_max": 6096.0, "clamp_neg": True,
    },
    # Lifted index: -8 to +4 (well-known meteorological scale)
    "lifted_index": {
        "ramp": "instability", "scale_min": -8.0, "scale_max": 4.0, "clamp_neg": False,
    },
    # Cloud cover: 0 to 100%
    "cloud_cover": {
        "ramp": "cloud", "scale_min": 0.0, "scale_max": 100.0, "clamp_neg": False,
    },
    # Precipitation: 0 to 50 mm
    "precipitation": {
        "ramp": "precip", "scale_min": 0.0, "scale_max": 50.0, "clamp_neg": True,
    },
    # Surface wind: 0 to 30 m/s (~58 kt)
    "wind_speed_10m": {
        "ramp": "wind", "scale_min": 0.0, "scale_max": 30.0, "clamp_neg": True,
    },
    # 850 hPa wind: 0 to 40 m/s (~78 kt)
    "wind_speed_850hPa": {
        "ramp": "wind", "scale_min": 0.0, "scale_max": 40.0, "clamp_neg": True,
    },
    # 700 hPa wind: 0 to 50 m/s (~97 kt)
    "wind_speed_700hPa": {
        "ramp": "wind", "scale_min": 0.0, "scale_max": 50.0, "clamp_neg": True,
    },
    # 500 hPa wind: 0 to 60 m/s (~117 kt)
    "wind_speed_500hPa": {
        "ramp": "wind", "scale_min": 0.0, "scale_max": 60.0, "clamp_neg": True,
    },
}


def _build_color_stops(
    ramp: list[tuple[float, int, int, int, int]],
    vmin: float,
    vmax: float,
) -> list[tuple[float, int, int, int, int]]:
    """Expand a fractional ramp into absolute-value color stops."""
    span = vmax - vmin if vmax != vmin else 1.0
    return [(vmin + frac * span, r, g, b, a) for frac, r, g, b, a in ramp]


def _colorize_array(
    data: Any,
    stops: list[tuple[float, int, int, int, int]],
) -> bytes:
    """Vectorized: map a 2-D float array to RGBA bytes via discrete stepped coloring.

    Each value is assigned the solid color of its floor color stop — no blending.
    For value V between stop[i] and stop[i+1], the color of stop[i] is used.
    """
    flat = data.ravel().astype(np.float64)
    n = len(flat)
    nan_mask = np.isnan(flat)

    positions = np.array([s[0] for s in stops], dtype=np.float64)
    r_stops = np.array([s[1] for s in stops], dtype=np.uint8)
    g_stops = np.array([s[2] for s in stops], dtype=np.uint8)
    b_stops = np.array([s[3] for s in stops], dtype=np.uint8)
    a_stops = np.array([s[4] for s in stops], dtype=np.uint8)

    # Floor-step: searchsorted(side='right') - 1 gives the lower boundary index
    indices = np.searchsorted(positions, flat, side='right') - 1
    indices = np.clip(indices, 0, len(stops) - 1)

    rgba = np.zeros(n * 4, dtype=np.uint8)
    rgba[0::4] = r_stops[indices]
    rgba[1::4] = g_stops[indices]
    rgba[2::4] = b_stops[indices]
    rgba[3::4] = a_stops[indices]

    # NaN pixels → fully transparent
    rgba[np.repeat(nan_mask, 4)] = 0

    return bytes(rgba)


def _make_png(width: int, height: int, rgba: bytes) -> bytes:
    """Minimal dependency-free PNG encoder (RGBA, 8-bit per channel)."""
    import struct
    import zlib

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type: None
        raw.extend(rgba[y * stride: (y + 1) * stride])
    idat = chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _fetch_raster(model: str, run_date: str, run_hour: str, fxx: int, variable: str) -> dict:
    """Synchronous Herbie fetch for raster — runs in thread pool.

    Returns a dict with keys: image (data-URI), coordinates, meta.
    """
    import base64
    from herbie import Herbie

    cfg = MODEL_CONFIG[model]
    vdef = VARIABLES[variable]
    product = vdef["product_overrides"].get(model, cfg["default_product"])

    dt_str = f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:8]} {run_hour}:00"

    kwargs: dict[str, Any] = {"date": dt_str, "model": cfg["herbie_model"], "fxx": fxx}
    if product:
        kwargs["product"] = product

    try:
        H = Herbie(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"Herbie init failed for {model} {dt_str} f{fxx:02d}: {exc}")

    step = RASTER_SUBSAMPLE.get(model, 6)

    # Fetch raw data arrays
    if vdef.get("is_wind_speed"):
        try:
            ds_u = H.xarray(vdef["search"])
            ds_v = H.xarray(vdef["search_v"])
        except Exception as exc:
            raise RuntimeError(f"Herbie xarray failed: {exc}")
        u_name = list(ds_u.data_vars)[0]
        v_name = list(ds_v.data_vars)[0]
        u_arr = ds_u[u_name].values
        v_arr = ds_v[v_name].values
        arr = np.sqrt(u_arr ** 2 + v_arr ** 2)
        lats = ds_u.latitude.values
        lons = ds_u.longitude.values
    elif variable in ("thermal_updraft", "soaring_quality", "bsratio"):
        # Derived soaring variables — need multiple fields, graceful fallback
        from app.services.soaring_derivation import (
            compute_wstar,
            compute_wstar_cape_fallback,
            compute_soaring_quality,
            compute_bsratio,
        )

        def _safe_fetch(key: str) -> np.ndarray | None:
            if key not in vdef:
                return None
            try:
                _ds = H.xarray(vdef[key])
                return _ds[list(_ds.data_vars)[0]].values
            except Exception:
                return None

        # Primary: SHTFL (may be missing at fh=0 for GFS/NAM)
        shtfl_arr = _safe_fetch("search")
        blh_arr = _safe_fetch("search_blh")
        t2m_arr = _safe_fetch("search_t2m")
        td2m_arr = _safe_fetch("search_td2m")
        tcdc_arr = _safe_fetch("search_tcdc")
        cape_arr = _safe_fetch("search_cape")

        # We need at least one dataset for lat/lon grid — try T2m, BLH, or SHTFL
        ref_ds = None
        for _key in ("search_t2m", "search_blh", "search"):
            if _key in vdef:
                try:
                    ref_ds = H.xarray(vdef[_key])
                    break
                except Exception:
                    continue
        if ref_ds is None:
            raise RuntimeError("Could not fetch any field for lat/lon grid")
        lats = ref_ds.latitude.values
        lons = ref_ds.longitude.values
        _grid_shape = lats.shape if lats.ndim == 2 else (len(lats),)

        # Defaults for missing fields
        if t2m_arr is None:
            t2m_arr = np.full(_grid_shape, 288.0)
        if td2m_arr is None:
            td2m_arr = t2m_arr - 10.0
        if tcdc_arr is None:
            tcdc_arr = np.zeros(_grid_shape)
        if blh_arr is None:
            blh_arr = np.full(_grid_shape, 1500.0)  # reasonable afternoon default

        shtfl_ok = shtfl_arr is not None and float(np.nanmax(shtfl_arr)) > 0.01

        if shtfl_ok:
            shtfl = np.maximum(shtfl_arr, 0.0)
            wstar = compute_wstar(shtfl, blh_arr, t2m_arr, td2m_arr, tcdc_arr)
        elif cape_arr is not None and float(np.nanmax(cape_arr)) > 1.0:
            wstar = compute_wstar_cape_fallback(cape_arr, blh_arr, t2m_arr, td2m_arr, tcdc_arr)
        else:
            wstar = np.zeros(_grid_shape)

        if variable == "soaring_quality":
            wind_sfc = None
            u_arr = _safe_fetch("search_wind_u")
            v_arr = _safe_fetch("search_wind_v")
            if u_arr is not None and v_arr is not None:
                wind_sfc = np.sqrt(u_arr ** 2 + v_arr ** 2)
            arr = compute_soaring_quality(wstar, blh_arr, tcdc_arr, wind_sfc)
        elif variable == "bsratio":
            wind_bl_u = _safe_fetch("search_wind_bl_u")
            wind_bl_v = _safe_fetch("search_wind_bl_v")
            wind_sfc_u = _safe_fetch("search_wind_u")
            wind_sfc_v = _safe_fetch("search_wind_v")
            if (wind_bl_u is not None and wind_bl_v is not None
                    and wind_sfc_u is not None and wind_sfc_v is not None):
                arr = compute_bsratio(wstar, wind_bl_u, wind_bl_v, wind_sfc_u, wind_sfc_v)
            else:
                arr = wstar
        else:
            arr = wstar
    else:
        try:
            ds = H.xarray(vdef["search"])
        except Exception as exc:
            raise RuntimeError(f"Herbie xarray failed: {exc}")
        var_names = list(ds.data_vars)
        if not var_names:
            raise RuntimeError("No data variable in dataset")
        arr = ds[var_names[0]].values
        if variable == "vertical_velocity_700hPa":
            arr = -arr / 10.0
        lats = ds.latitude.values
        lons = ds.longitude.values

    # Normalize longitudes > 180
    lons = np.where(lons > 180, lons - 360, lons)

    is_2d = lats.ndim == 2

    if is_2d:
        # Subsample both dimensions
        row_idx = np.arange(0, lats.shape[0], step)
        col_idx = np.arange(0, lats.shape[1], step)
        lats_sub = lats[np.ix_(row_idx, col_idx)]
        lons_sub = lons[np.ix_(row_idx, col_idx)]
        data_sub = arr[np.ix_(row_idx, col_idx)]
        height_px = lats_sub.shape[0]
        width_px = lats_sub.shape[1]

        # Detect if rows are south-to-north (first row has smaller lat)
        if lats_sub[0, 0] < lats_sub[-1, 0]:
            data_sub = np.flipud(data_sub)
            lats_sub = np.flipud(lats_sub)
            lons_sub = np.flipud(lons_sub)

        # Use cell EDGES (not centers) — expand by half a grid cell in each direction.
        # For 2D grids, estimate cell spacing from adjacent points.
        half_dlat = abs(float(lats_sub[0, 0] - lats_sub[1, 0])) / 2 if height_px > 1 else 0.015
        half_dlon = abs(float(lons_sub[0, 1] - lons_sub[0, 0])) / 2 if width_px > 1 else 0.015
        n_lat = float(np.max(lats_sub)) + half_dlat
        s_lat = float(np.min(lats_sub)) - half_dlat
        w_lon = float(np.min(lons_sub)) - half_dlon
        e_lon = float(np.max(lons_sub)) + half_dlon
    else:
        # 1-D lat/lon arrays
        lat_idx = np.arange(0, len(lats), step)
        lon_idx = np.arange(0, len(lons), step)
        lats_1d = lats[lat_idx]
        lons_1d = lons[lon_idx]
        data_sub = arr[np.ix_(lat_idx, lon_idx)] if arr.ndim == 2 else arr[lat_idx]

        # Clip global grids (e.g. GFS) to CONUS bounds to avoid MapLibre
        # projection errors with full-globe coordinates
        CONUS_LAT = (20.0, 55.0)
        CONUS_LON = (-130.0, -60.0)
        if float(lats_1d.min()) < CONUS_LAT[0] or float(lats_1d.max()) > CONUS_LAT[1]:
            lat_mask = (lats_1d >= CONUS_LAT[0]) & (lats_1d <= CONUS_LAT[1])
            lon_mask = (lons_1d >= CONUS_LON[0]) & (lons_1d <= CONUS_LON[1])
            lats_1d = lats_1d[lat_mask]
            lons_1d = lons_1d[lon_mask]
            data_sub = data_sub[np.ix_(np.where(lat_mask)[0], np.where(lon_mask)[0])]

        height_px = len(lats_1d)
        width_px = len(lons_1d)

        # Use cell EDGES (not centers) so the image aligns correctly.
        # Each pixel represents a grid cell; the image boundary should be
        # half a cell beyond the outermost grid-point centers.
        half_dlat = abs(float(lats_1d[1] - lats_1d[0])) / 2 if len(lats_1d) > 1 else 0.125
        half_dlon = abs(float(lons_1d[1] - lons_1d[0])) / 2 if len(lons_1d) > 1 else 0.125
        n_lat = float(lats_1d.max()) + half_dlat
        s_lat = float(lats_1d.min()) - half_dlat
        w_lon = float(lons_1d.min()) - half_dlon
        e_lon = float(lons_1d.max()) + half_dlon

        # Ensure first image row = northernmost lat
        if lats_1d[0] < lats_1d[-1]:
            data_sub = np.flipud(data_sub)

    # --- Fixed color scaling — same colors every day for cross-day comparison ---
    vcfg = _VAR_SCALE.get(variable, {
        "ramp": "thermal", "scale_min": 0.0, "scale_max": 1.0, "clamp_neg": False,
    })
    ramp = _COLOR_RAMPS.get(vcfg["ramp"], _COLOR_RAMPS["thermal"])

    # Clamp negative values to zero for positive-only variables
    if vcfg["clamp_neg"]:
        data_sub = np.where(np.isnan(data_sub), data_sub, np.maximum(data_sub, 0.0))

    valid_data = data_sub[~np.isnan(data_sub)]
    if valid_data.size == 0:
        raise RuntimeError("No valid data in grid")

    data_min = float(np.nanmin(valid_data))
    data_max = float(np.nanmax(valid_data))
    data_mean = float(np.nanmean(valid_data))

    scale_min = vcfg["scale_min"]
    scale_max = vcfg["scale_max"]

    stops = _build_color_stops(ramp, scale_min, scale_max)

    # Vectorized color mapping
    rgba_bytes = _colorize_array(data_sub, stops)
    png_bytes = _make_png(width_px, height_px, rgba_bytes)
    data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode()

    # MapLibre image source coordinates: [[w,n],[e,n],[e,s],[w,s]]
    coordinates = [
        [round(w_lon, 4), round(n_lat, 4)],
        [round(e_lon, 4), round(n_lat, 4)],
        [round(e_lon, 4), round(s_lat, 4)],
        [round(w_lon, 4), round(s_lat, 4)],
    ]

    # Build tier info for frontend legend: each tier's value boundary + color
    tiers = []
    for i, (val, r_, g_, b_, a_) in enumerate(stops):
        physical_val = scale_min + val * (scale_max - scale_min)
        tiers.append({
            "value": round(physical_val, 4),
            "color": f"rgba({int(r_)},{int(g_)},{int(b_)},{round(a_/255,2)})",
        })

    return {
        "image": data_uri,
        "coordinates": coordinates,
        "data_range": {
            "min": round(data_min, 4),
            "max": round(data_max, 4),
            "mean": round(data_mean, 4),
            "scale_min": round(scale_min, 4),
            "scale_max": round(scale_max, 4),
        },
        "tiers": tiers,
        "meta": {
            "model": model,
            "variable": variable,
            "run": f"{run_date}T{run_hour}:00Z",
            "fxx": fxx,
            "width": width_px,
            "height": height_px,
        },
    }


def _build_geojson(lats: Any, lons: Any, data: Any, step: int) -> list[dict]:
    """Convert grid arrays to GeoJSON features, subsampling every `step` points."""
    features: list[dict] = []
    if lats.ndim == 2:
        for i in range(0, lats.shape[0], step):
            for j in range(0, lats.shape[1], step):
                val = float(data[i, j])
                if np.isnan(val):
                    continue
                lat_v = float(lats[i, j])
                lon_v = float(lons[i, j])
                if lon_v > 180:
                    lon_v -= 360
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [round(lon_v, 3), round(lat_v, 3)]},
                    "properties": {"value": round(val, 2)},
                })
    else:
        for i in range(0, len(lats), step):
            for j in range(0, len(lons), step):
                val = float(data[i, j]) if data.ndim > 1 else float(data[i])
                if np.isnan(val):
                    continue
                lon_v = float(lons[j])
                if lon_v > 180:
                    lon_v -= 360
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [round(lon_v, 3), round(float(lats[i]), 3)]},
                    "properties": {"value": round(val, 2)},
                })
    return features


def _fetch_grid(model: str, run_date: str, run_hour: str, fxx: int, variable: str, step_override: int | None = None) -> dict:
    """Synchronous Herbie fetch — runs in thread pool."""
    from herbie import Herbie

    cfg = MODEL_CONFIG[model]
    vdef = VARIABLES[variable]
    product = vdef["product_overrides"].get(model, cfg["default_product"])

    dt_str = f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:8]} {run_hour}:00"

    kwargs: dict[str, Any] = {"date": dt_str, "model": cfg["herbie_model"], "fxx": fxx}
    if product:
        kwargs["product"] = product

    try:
        H = Herbie(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"Herbie init failed for {model} {dt_str} f{fxx:02d}: {exc}")

    step = step_override if step_override is not None else SUBSAMPLE.get(model, 10)

    # Wind speed: fetch U and V components, compute sqrt(u^2 + v^2)
    if vdef.get("is_wind_speed"):
        try:
            ds_u = H.xarray(vdef["search"])
            ds_v = H.xarray(vdef["search_v"])
        except Exception as exc:
            raise RuntimeError(f"Herbie xarray failed: {exc}")

        u_name = list(ds_u.data_vars)[0]
        v_name = list(ds_v.data_vars)[0]
        u_arr = ds_u[u_name].values
        v_arr = ds_v[v_name].values
        speed = np.sqrt(u_arr ** 2 + v_arr ** 2)

        lats = ds_u.latitude.values
        lons = ds_u.longitude.values
        features = _build_geojson(lats, lons, speed, step)
    elif variable in ("thermal_updraft", "soaring_quality", "bsratio"):
        # Derived soaring variables — graceful fallback for missing SHTFL
        from app.services.soaring_derivation import (
            compute_wstar,
            compute_wstar_cape_fallback,
            compute_soaring_quality,
            compute_bsratio,
        )

        def _safe_fetch_gj(key: str) -> np.ndarray | None:
            if key not in vdef:
                return None
            try:
                _ds = H.xarray(vdef[key])
                return _ds[list(_ds.data_vars)[0]].values
            except Exception:
                return None

        shtfl_arr = _safe_fetch_gj("search")
        blh_arr = _safe_fetch_gj("search_blh")
        t2m_arr = _safe_fetch_gj("search_t2m")
        td2m_arr = _safe_fetch_gj("search_td2m")
        tcdc_arr = _safe_fetch_gj("search_tcdc")
        cape_arr = _safe_fetch_gj("search_cape")

        ref_ds = None
        for _key in ("search_t2m", "search_blh", "search"):
            if _key in vdef:
                try:
                    ref_ds = H.xarray(vdef[_key])
                    break
                except Exception:
                    continue
        if ref_ds is None:
            raise RuntimeError("Could not fetch any field for lat/lon grid")
        lats = ref_ds.latitude.values
        lons = ref_ds.longitude.values
        _grid_shape = lats.shape if lats.ndim == 2 else (len(lats),)

        if t2m_arr is None:
            t2m_arr = np.full(_grid_shape, 288.0)
        if td2m_arr is None:
            td2m_arr = t2m_arr - 10.0
        if tcdc_arr is None:
            tcdc_arr = np.zeros(_grid_shape)
        if blh_arr is None:
            blh_arr = np.full(_grid_shape, 1500.0)

        shtfl_ok = shtfl_arr is not None and float(np.nanmax(shtfl_arr)) > 0.01

        if shtfl_ok:
            shtfl = np.maximum(shtfl_arr, 0.0)
            wstar = compute_wstar(shtfl, blh_arr, t2m_arr, td2m_arr, tcdc_arr)
        elif cape_arr is not None and float(np.nanmax(cape_arr)) > 1.0:
            wstar = compute_wstar_cape_fallback(cape_arr, blh_arr, t2m_arr, td2m_arr, tcdc_arr)
        else:
            wstar = np.zeros(_grid_shape)

        if variable == "soaring_quality":
            wind_sfc = None
            u_arr = _safe_fetch_gj("search_wind_u")
            v_arr = _safe_fetch_gj("search_wind_v")
            if u_arr is not None and v_arr is not None:
                wind_sfc = np.sqrt(u_arr ** 2 + v_arr ** 2)
            arr = compute_soaring_quality(wstar, blh_arr, tcdc_arr, wind_sfc)
        elif variable == "bsratio":
            wind_bl_u = _safe_fetch_gj("search_wind_bl_u")
            wind_bl_v = _safe_fetch_gj("search_wind_bl_v")
            wind_sfc_u = _safe_fetch_gj("search_wind_u")
            wind_sfc_v = _safe_fetch_gj("search_wind_v")
            if (wind_bl_u is not None and wind_bl_v is not None
                    and wind_sfc_u is not None and wind_sfc_v is not None):
                arr = compute_bsratio(wstar, wind_bl_u, wind_bl_v, wind_sfc_u, wind_sfc_v)
            else:
                arr = wstar
        else:
            arr = wstar

        features = _build_geojson(lats, lons, arr, step)
    else:
        try:
            ds = H.xarray(vdef["search"])
        except Exception as exc:
            raise RuntimeError(f"Herbie xarray failed: {exc}")

        var_names = list(ds.data_vars)
        if not var_names:
            raise RuntimeError("No data variable in dataset")

        arr = ds[var_names[0]].values

        if variable == "vertical_velocity_700hPa":
            arr = -arr / 10.0

        lats = ds.latitude.values
        lons = ds.longitude.values
        features = _build_geojson(lats, lons, arr, step)

    vcfg = _VAR_SCALE.get(variable, {"scale_min": 0, "scale_max": 1})
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "model": model,
            "variable": variable,
            "run": f"{run_date}T{run_hour}:00Z",
            "fxx": fxx,
            "scale_min": vcfg.get("scale_min", 0),
            "scale_max": vcfg.get("scale_max", 1),
        },
    }


# ---------------------------------------------------------------------------
# Point value extraction (single nearest grid-point, no raster PNG)
# ---------------------------------------------------------------------------

def _fetch_point_value(model: str, run_date: str, run_hour: str, fxx: int, variable: str, lat: float, lng: float) -> float:
    """Extract the nearest-grid-point value for a single model/variable.

    Reuses the same Herbie fetch logic as _fetch_raster but returns a scalar.
    """
    from herbie import Herbie

    cfg = MODEL_CONFIG[model]
    vdef = VARIABLES[variable]
    product = vdef["product_overrides"].get(model, cfg["default_product"])

    dt_str = f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:8]} {run_hour}:00"

    kwargs: dict[str, Any] = {"date": dt_str, "model": cfg["herbie_model"], "fxx": fxx}
    if product:
        kwargs["product"] = product

    H = Herbie(**kwargs)

    def _nearest(lats_arr: Any, lons_arr: Any, data_arr: Any) -> float:
        """Find the single nearest grid point and return its value."""
        lons_norm = np.where(lons_arr > 180, lons_arr - 360, lons_arr)
        dlat = lats_arr - lat
        dlng = lons_norm - lng
        dist2 = dlat ** 2 + dlng ** 2
        idx = int(np.nanargmin(dist2))
        return float(data_arr.ravel()[idx])

    if vdef.get("is_wind_speed"):
        ds_u = H.xarray(vdef["search"])
        ds_v = H.xarray(vdef["search_v"])
        u_arr = ds_u[list(ds_u.data_vars)[0]].values
        v_arr = ds_v[list(ds_v.data_vars)[0]].values
        arr = np.sqrt(u_arr ** 2 + v_arr ** 2)
        lats_arr = ds_u.latitude.values
        lons_arr = ds_u.longitude.values
        return _nearest(lats_arr, lons_arr, arr)

    if variable in ("thermal_updraft", "soaring_quality", "bsratio"):
        from app.services.soaring_derivation import (
            compute_wstar,
            compute_wstar_cape_fallback,
            compute_soaring_quality,
            compute_bsratio,
        )

        def _sf(key: str) -> np.ndarray | None:
            if key not in vdef:
                return None
            try:
                _ds = H.xarray(vdef[key])
                return _ds[list(_ds.data_vars)[0]].values
            except Exception:
                return None

        shtfl_arr = _sf("search")
        blh_arr   = _sf("search_blh")
        t2m_arr   = _sf("search_t2m")
        td2m_arr  = _sf("search_td2m")
        tcdc_arr  = _sf("search_tcdc")
        cape_arr  = _sf("search_cape")

        ref_ds = None
        for _key in ("search_t2m", "search_blh", "search"):
            if _key in vdef:
                try:
                    ref_ds = H.xarray(vdef[_key])
                    break
                except Exception:
                    continue
        if ref_ds is None:
            raise RuntimeError("Could not fetch any field for lat/lon grid")

        lats_arr = ref_ds.latitude.values
        lons_arr = ref_ds.longitude.values
        _shape = lats_arr.shape if lats_arr.ndim == 2 else (len(lats_arr),)

        if t2m_arr is None:
            t2m_arr = np.full(_shape, 288.0)
        if td2m_arr is None:
            td2m_arr = t2m_arr - 10.0
        if tcdc_arr is None:
            tcdc_arr = np.zeros(_shape)
        if blh_arr is None:
            blh_arr = np.full(_shape, 1500.0)

        shtfl_ok = shtfl_arr is not None and float(np.nanmax(shtfl_arr)) > 0.01
        if shtfl_ok:
            wstar = compute_wstar(np.maximum(shtfl_arr, 0.0), blh_arr, t2m_arr, td2m_arr, tcdc_arr)
        elif cape_arr is not None and float(np.nanmax(cape_arr)) > 1.0:
            wstar = compute_wstar_cape_fallback(cape_arr, blh_arr, t2m_arr, td2m_arr, tcdc_arr)
        else:
            wstar = np.zeros(_shape)

        if variable == "soaring_quality":
            u_arr = _sf("search_wind_u")
            v_arr = _sf("search_wind_v")
            wind_sfc = np.sqrt(u_arr ** 2 + v_arr ** 2) if (u_arr is not None and v_arr is not None) else None
            arr = compute_soaring_quality(wstar, blh_arr, tcdc_arr, wind_sfc)
        elif variable == "bsratio":
            bl_u = _sf("search_wind_bl_u")
            bl_v = _sf("search_wind_bl_v")
            sf_u = _sf("search_wind_u")
            sf_v = _sf("search_wind_v")
            if bl_u is not None and bl_v is not None and sf_u is not None and sf_v is not None:
                arr = compute_bsratio(wstar, bl_u, bl_v, sf_u, sf_v)
            else:
                arr = wstar
        else:
            arr = wstar

        return _nearest(lats_arr, lons_arr, arr)

    # Simple single-field fetch
    ds = H.xarray(vdef["search"])
    arr = ds[list(ds.data_vars)[0]].values
    if variable == "vertical_velocity_700hPa":
        arr = -arr / 10.0
    lats_arr = ds.latitude.values
    lons_arr = ds.longitude.values
    return _nearest(lats_arr, lons_arr, arr)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/models")
async def weather_models():
    """List available weather models."""
    return JSONResponse({
        "models": [
            {
                "id": k,
                "label": v["label"],
                "resolution": v["resolution"],
                "coverage": v["coverage"],
                "run_hours": v["run_hours"],
                "max_fxx": v["max_fxx"],
                "fxx_step": v["fxx_step"],
            }
            for k, v in MODEL_CONFIG.items()
        ]
    })


@router.get("/available")
async def weather_available(model: str = Query(..., description="Model id")):
    """Return recent runs and their valid forecast times for a model."""
    if model not in MODEL_CONFIG:
        raise HTTPException(400, f"Unknown model: {model}")

    cfg = MODEL_CONFIG[model]
    now = datetime.now(timezone.utc)

    runs: list[dict[str, Any]] = []
    for day_offset in range(2):
        dt = now - timedelta(days=day_offset)
        date_str = dt.strftime("%Y%m%d")
        for rh in sorted(cfg["run_hours"], reverse=True):
            run_dt = dt.replace(hour=rh, minute=0, second=0, microsecond=0)
            if run_dt > now:
                continue
            # Allow ~3h for data to appear on AWS after run time
            if (now - run_dt).total_seconds() < 10800:
                continue
            valid_times: list[str] = []
            for fh in range(0, cfg["max_fxx"] + 1, cfg["fxx_step"]):
                vt = run_dt + timedelta(hours=fh)
                valid_times.append(vt.strftime("%Y-%m-%dT%H:%M:%SZ"))
            runs.append({
                "date": date_str,
                "hour": f"{rh:02d}",
                "valid_times": valid_times,
                "max_fxx": cfg["max_fxx"],
                "fxx_step": cfg["fxx_step"],
            })

    # Return last 6 runs
    return JSONResponse({"model": model, "runs": runs[:6]})


@router.get("/grid")
async def weather_grid(
    model: str = Query(...),
    date: str = Query(..., description="YYYYMMDD"),
    hour: str = Query(..., description="Run hour e.g. 12"),
    fh: int = Query(..., description="Forecast hour"),
    variable: str = Query(..., description="Variable name"),
    step: int | None = Query(None, description="Override subsample step (1=full resolution)"),
    lat_min: float | None = Query(None), lat_max: float | None = Query(None),
    lon_min: float | None = Query(None), lon_max: float | None = Query(None),
):
    """Fetch a model grid via Herbie and return subsampled GeoJSON."""
    if model not in MODEL_CONFIG:
        raise HTTPException(400, f"Unknown model: {model}")
    if variable not in VARIABLES:
        raise HTTPException(400, f"Unknown variable: {variable}")
    if model in VARIABLES[variable].get("exclude_models", []):
        raise HTTPException(400, f"Variable {variable} not available for {model}")

    def _clip_features(data: dict) -> dict:
        if lat_min is None or lat_max is None or lon_min is None or lon_max is None:
            return data
        clipped = [
            f for f in data["features"]
            if lat_min <= f["geometry"]["coordinates"][1] <= lat_max
            and lon_min <= f["geometry"]["coordinates"][0] <= lon_max
        ]
        return {**data, "features": clipped}

    # No caching — always fetch live data for debugging
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor, _fetch_grid, model, date, hour, fh, variable, step
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Unexpected error: {exc}")

    return JSONResponse(_clip_features(result))


@router.get("/raster")
async def weather_raster(
    model: str = Query(...),
    date: str = Query(..., description="YYYYMMDD"),
    hour: str = Query(..., description="Run hour e.g. 12"),
    fh: int = Query(..., description="Forecast hour"),
    variable: str = Query(..., description="Variable name"),
):
    """Fetch a model grid via Herbie and return a PNG raster with color mapping.

    Response JSON:
      {
        "image": "data:image/png;base64,...",
        "coordinates": [[w,n],[e,n],[e,s],[w,s]],
        "meta": {...}
      }

    Coordinates are in MapLibre image source format (top-left, top-right,
    bottom-right, bottom-left).
    """
    if model not in MODEL_CONFIG:
        raise HTTPException(400, f"Unknown model: {model}")
    if variable not in VARIABLES:
        raise HTTPException(400, f"Unknown variable: {variable}")
    if model in VARIABLES[variable].get("exclude_models", []):
        raise HTTPException(400, f"Variable {variable} not available for {model}")

    # Version suffix — bump when raster generation logic changes to invalidate cache
    _RASTER_VERSION = "v12"
    cache_key = f"raster:{_RASTER_VERSION}:{model}:{date}:{hour}:{fh}:{variable}"

    # Check persistent cache first
    cached = get_cached_raster(cache_key)
    if cached is not None:
        return JSONResponse(cached)

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor, _fetch_raster, model, date, hour, fh, variable
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Unexpected error: {exc}")

    # Store in persistent cache
    try:
        store_raster(cache_key, model, date, hour, fh, variable, result)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Cache store failed for %s", cache_key, exc_info=True)

    # Record demand so the scheduler can pre-warm this model/variable next cycle.
    try:
        from app.services.demand_tracker import record_view as _record_demand_view
        _record_demand_view(model, variable)
    except Exception:
        pass  # demand tracking is best-effort; never block the response

    return JSONResponse(result)


@router.get("/point")
async def weather_point(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    variable: str = Query(..., description="Variable name"),
    date: str = Query(..., description="YYYYMMDD run date"),
    hour: str = Query(..., description="Run hour e.g. 06"),
    fh: int = Query(..., description="Forecast hour"),
):
    """Return the nearest-grid-point value for every applicable model.

    Runs all model fetches in parallel via ThreadPoolExecutor and returns JSON:
    {
      "variable": "thermal_updraft",
      "lat": 39.0,
      "lng": -75.8,
      "values": [
        {"model": "gfs", "label": "GFS", "value": 3.13, "unit": "m/s"},
        ...
      ]
    }

    Models that are excluded for this variable or whose fetch fails are omitted
    from the results silently (frontend handles missing models gracefully).
    """
    if variable not in VARIABLES:
        raise HTTPException(400, f"Unknown variable: {variable}")

    vdef = VARIABLES[variable]
    excluded = set(vdef.get("exclude_models", []))
    applicable = [m for m in MODEL_CONFIG if m not in excluded]

    # Determine SI unit string for this variable
    _UNITS: dict[str, str] = {
        "thermal_updraft": "m/s",
        "soaring_quality": "",
        "bsratio": "",
        "cape": "J/kg",
        "boundary_layer_height": "m",
        "convective_cloud_top": "m",
        "convective_cloud_base": "m",
        "lifted_index": "",
        "cloud_cover": "%",
        "precipitation": "mm",
        "vertical_velocity_700hPa": "m/s",
        "wind_speed_10m": "m/s",
        "wind_speed_850hPa": "m/s",
        "wind_speed_700hPa": "m/s",
        "wind_speed_500hPa": "m/s",
    }
    unit = _UNITS.get(variable, "")

    loop = asyncio.get_event_loop()

    async def _fetch_one(model: str) -> dict | None:
        try:
            val = await loop.run_in_executor(
                _executor, _fetch_point_value, model, date, hour, fh, variable, lat, lng
            )
            if np.isnan(val):
                return None
            return {
                "model": model,
                "label": MODEL_CONFIG[model]["label"],
                "value": round(float(val), 4),
                "unit": unit,
            }
        except Exception:
            return None

    results = await asyncio.gather(*[_fetch_one(m) for m in applicable])
    values = [r for r in results if r is not None]

    # Preserve display order matching MODEL_IDS
    order = {m: i for i, m in enumerate(["gfs", "nam3km", "nam", "rap", "hrrr", "nbm"])}
    values.sort(key=lambda r: order.get(r["model"], 99))

    return JSONResponse({
        "variable": variable,
        "lat": lat,
        "lng": lng,
        "values": values,
    })


@router.get("/variables")
async def weather_variables():
    """List available overlay variables."""
    return JSONResponse({
        "variables": [
            {
                "id": k,
                "is_wind_speed": v.get("is_wind_speed", False),
                "exclude_models": v.get("exclude_models", []),
            }
            for k, v in VARIABLES.items()
        ]
    })


# ---------------------------------------------------------------------------
# Wind barb search strings per level
# ---------------------------------------------------------------------------
_WIND_BARB_LEVELS: dict[str, tuple[str, str, dict[str, str]]] = {
    # level_id -> (ugrd_search, vgrd_search, product_overrides)
    "10m":    (":UGRD:10 m above ground:", ":VGRD:10 m above ground:", {}),
    "975hPa": (":UGRD:975 mb:",            ":VGRD:975 mb:",            {"hrrr": "prs"}),
    "950hPa": (":UGRD:950 mb:",            ":VGRD:950 mb:",            {"hrrr": "prs"}),
    "925hPa": (":UGRD:925 mb:",            ":VGRD:925 mb:",            {"hrrr": "prs"}),
    "900hPa": (":UGRD:900 mb:",            ":VGRD:900 mb:",            {"hrrr": "prs"}),
    "850hPa": (":UGRD:850 mb:",            ":VGRD:850 mb:",            {"hrrr": "prs"}),
    "800hPa": (":UGRD:800 mb:",            ":VGRD:800 mb:",            {"hrrr": "prs"}),
    "700hPa": (":UGRD:700 mb:",            ":VGRD:700 mb:",            {"hrrr": "prs"}),
    "600hPa": (":UGRD:600 mb:",            ":VGRD:600 mb:",            {"hrrr": "prs"}),
    "500hPa": (":UGRD:500 mb:",            ":VGRD:500 mb:",            {"hrrr": "prs"}),
}

# No subsampling — send every grid point, frontend handles density
_BARB_STEP = 1

# CONUS clip bounds — same as raster pipeline
_BARB_LAT = (20.0, 55.0)
_BARB_LON = (-130.0, -60.0)


def _fetch_wind_barbs(
    model: str,
    run_date: str,
    run_hour: str,
    fxx: int,
    level: str,
) -> list[dict]:
    """Synchronous Herbie fetch for U/V wind components.

    Returns a list of {lat, lng, u, v} dicts subsampled to ~_BARB_TARGET points.
    Runs in the thread-pool executor.
    """
    from herbie import Herbie

    if level not in _WIND_BARB_LEVELS:
        raise RuntimeError(f"Unknown wind barb level: {level}")

    ugrd_search, vgrd_search, prod_overrides = _WIND_BARB_LEVELS[level]

    cfg = MODEL_CONFIG[model]
    default_product = cfg["default_product"]
    product = prod_overrides.get(model, default_product)

    dt_str = f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:8]} {run_hour}:00"

    kwargs: dict[str, Any] = {"date": dt_str, "model": cfg["herbie_model"], "fxx": fxx}
    if product:
        kwargs["product"] = product

    try:
        H = Herbie(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"Herbie init failed for {model} {dt_str} f{fxx:02d}: {exc}")

    try:
        ds_u = H.xarray(ugrd_search)
        ds_v = H.xarray(vgrd_search)
    except Exception as exc:
        raise RuntimeError(f"Herbie wind barb fetch failed: {exc}")

    u_arr = ds_u[list(ds_u.data_vars)[0]].values
    v_arr = ds_v[list(ds_v.data_vars)[0]].values
    lats = ds_u.latitude.values
    lons = ds_u.longitude.values

    # Normalize longitudes
    lons = np.where(lons > 180, lons - 360, lons)

    is_2d = lats.ndim == 2

    if is_2d:
        rows, cols = lats.shape

        # Vectorised CONUS clip + NaN filter
        lat_flat = lats[::_BARB_STEP, ::_BARB_STEP].ravel()
        lon_flat = lons[::_BARB_STEP, ::_BARB_STEP].ravel()
        u_flat = u_arr[::_BARB_STEP, ::_BARB_STEP].ravel()
        v_flat = v_arr[::_BARB_STEP, ::_BARB_STEP].ravel()

        mask = (
            (lat_flat >= _BARB_LAT[0]) & (lat_flat <= _BARB_LAT[1]) &
            (lon_flat >= _BARB_LON[0]) & (lon_flat <= _BARB_LON[1]) &
            np.isfinite(u_flat) & np.isfinite(v_flat)
        )
        lat_sel = lat_flat[mask]
        lon_sel = lon_flat[mask]
        u_sel = u_flat[mask]
        v_sel = v_flat[mask]

        points: list[dict] = [
            {"lat": round(float(la), 3), "lng": round(float(lo), 3),
             "u": round(float(u), 3), "v": round(float(v), 3)}
            for la, lo, u, v in zip(lat_sel, lon_sel, u_sel, v_sel)
        ]
    else:
        lats_1d = lats
        lons_1d = lons

        # Clip to CONUS
        lat_mask = (lats_1d >= _BARB_LAT[0]) & (lats_1d <= _BARB_LAT[1])
        lon_mask = (lons_1d >= _BARB_LON[0]) & (lons_1d <= _BARB_LON[1])
        lat_sel = lats_1d[lat_mask][::_BARB_STEP]
        lon_sel = lons_1d[lon_mask][::_BARB_STEP]
        lat_idx = np.where(lat_mask)[0][::_BARB_STEP]
        lon_idx = np.where(lon_mask)[0][::_BARB_STEP]

        points = []
        for i in lat_idx:
            for j in lon_idx:
                u_v = float(u_arr[i, j]) if u_arr.ndim == 2 else float(u_arr[i])
                v_v = float(v_arr[i, j]) if v_arr.ndim == 2 else float(v_arr[i])
                if np.isnan(u_v) or np.isnan(v_v):
                    continue
                points.append({
                    "lat": round(float(lats_1d[i]), 3),
                    "lng": round(float(lons_1d[j]), 3),
                    "u": round(u_v, 3),
                    "v": round(v_v, 3),
                })

    return points


# In-memory cache for wind barbs (same TTL as grid cache)
_barb_cache: dict[str, tuple[list[dict], float]] = {}


@router.get("/wind-barbs")
async def weather_wind_barbs(
    model: str = Query(...),
    date: str = Query(..., description="YYYYMMDD"),
    hour: str = Query(..., description="Run hour e.g. 12"),
    fh: int = Query(..., description="Forecast hour"),
    level: str = Query("10m", description="Wind level: 10m, 975-500hPa"),
    lat_min: float | None = Query(None), lat_max: float | None = Query(None),
    lon_min: float | None = Query(None), lon_max: float | None = Query(None),
):
    """Return a subsampled grid of U/V wind components for drawing wind barbs.

    Response: {"points": [{lat, lng, u, v}, ...], "meta": {...}}
    u/v are in m/s. The frontend converts to knots/direction for rendering.
    """
    if model not in MODEL_CONFIG:
        raise HTTPException(400, f"Unknown model: {model}")
    if level not in _WIND_BARB_LEVELS:
        raise HTTPException(400, f"Unknown level: {level}. Valid: {list(_WIND_BARB_LEVELS)}")
    if model == "nbm":
        raise HTTPException(400, "Wind barbs not available for NBM")

    cache_key = f"barbs:{model}:{date}:{hour}:{fh}:{level}"
    now = time.time()

    def _clip_bbox(pts: list[dict]) -> list[dict]:
        if lat_min is None or lat_max is None or lon_min is None or lon_max is None:
            return pts
        return [p for p in pts if lat_min <= p["lat"] <= lat_max and lon_min <= p["lng"] <= lon_max]

    if cache_key in _barb_cache:
        pts, ts = _barb_cache[cache_key]
        if now - ts < GRID_TTL:
            clipped = _clip_bbox(pts)
            return JSONResponse({"points": clipped, "meta": {"model": model, "level": level, "fh": fh, "count": len(clipped)}})

    loop = asyncio.get_event_loop()
    try:
        points = await loop.run_in_executor(
            _executor, _fetch_wind_barbs, model, date, hour, fh, level
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Unexpected error: {exc}")

    _barb_cache[cache_key] = (points, now)

    # Prune stale barb cache entries
    for k, (_, ts) in list(_barb_cache.items()):
        if now - ts > GRID_TTL:
            del _barb_cache[k]

    clipped = _clip_bbox(points)
    return JSONResponse({
        "points": clipped,
        "meta": {"model": model, "level": level, "fh": fh, "count": len(clipped)},
    })
