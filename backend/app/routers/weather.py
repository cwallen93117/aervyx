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
    "nam": {
        "label": "NAM",
        "resolution": "3-12km",
        "coverage": "N. America",
        "herbie_model": "nam",
        "default_product": None,
        "run_hours": [0, 6, 12, 18],
        "max_fxx": 60,
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
    "hrrr": 20,
    "rap": 8,
    "gfs": 10,
    "nam": 12,
    "nbm": 15,
}

# Finer subsample steps for raster image (more pixels = better quality)
RASTER_SUBSAMPLE: dict[str, int] = {
    "hrrr": 8,
    "rap": 4,
    "gfs": 3,
    "nam": 5,
    "nbm": 6,
}

# Raster cache: key -> (json_dict, timestamp)
_raster_cache: dict[str, tuple[dict, float]] = {}

# ---------------------------------------------------------------------------
# Color ramp definitions for soaring weather visualization
# Each entry: list of (fraction, R, G, B, A) where fraction is 0.0-1.0.
# The actual value range is computed dynamically from data percentiles,
# so the ramp only defines the *shape* of the color progression.
# ---------------------------------------------------------------------------
# Ramp: position fraction (0-1) → (R, G, B, A)
_COLOR_RAMPS: dict[str, list[tuple[float, int, int, int, int]]] = {
    # thermal / updraft: light cyan→green→yellow-green→yellow→orange→red
    # Matches XC Skies style — visible even at low values
    "thermal": [
        (0.0,  180, 230, 235, 120),  # light cyan, visible
        (0.08, 150, 220, 200, 155),  # light teal
        (0.2,  110, 200, 130, 185),  # green
        (0.35, 170, 215, 70,  205),  # yellow-green
        (0.5,  210, 225, 45,  220),  # yellow
        (0.7,  235, 175, 25,  235),  # orange
        (1.0,  220, 45,  20,  245),  # red
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
    # height: gray→green→blue→purple→magenta
    "height": [
        (0.0,  140, 140, 140, 150),
        (0.25, 70,  190, 70,  180),
        (0.5,  80,  180, 220, 200),
        (0.75, 160, 80,  210, 215),
        (1.0,  220, 60,  200, 230),
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
        "ramp": "thermal", "scale_min": 0.0, "scale_max": 6.0, "clamp_neg": True,
    },
    # Composite soaring quality: 0 to 10
    "soaring_quality": {
        "ramp": "soaring", "scale_min": 0.0, "scale_max": 10.0, "clamp_neg": True,
    },
    # CAPE: 0 to 4000 J/kg
    "cape": {
        "ramp": "thermal", "scale_min": 0.0, "scale_max": 4000.0, "clamp_neg": True,
    },
    # Cloud top height: 0 to 5500 m (~18000 ft)
    "convective_cloud_top": {
        "ramp": "height", "scale_min": 0.0, "scale_max": 5500.0, "clamp_neg": True,
    },
    # Cloud base height: 0 to 5500 m (~18000 ft)
    "convective_cloud_base": {
        "ramp": "height", "scale_min": 0.0, "scale_max": 5500.0, "clamp_neg": True,
    },
    # Boundary layer height: 0 to 5500 m (~18000 ft)
    "boundary_layer_height": {
        "ramp": "height", "scale_min": 0.0, "scale_max": 5500.0, "clamp_neg": True,
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
    """Vectorized: map a 2-D float array to RGBA bytes via discrete color tiers.

    Each pixel gets the flat color of its tier (no gradient interpolation).
    This matches the XC Skies stepped/banded visualization style, producing
    clear boundaries between value ranges.
    """
    flat = data.ravel().astype(np.float64)
    n = len(flat)
    nan_mask = np.isnan(flat)
    # Pre-fill with transparent
    r = np.zeros(n, dtype=np.float64)
    g = np.zeros(n, dtype=np.float64)
    b = np.zeros(n, dtype=np.float64)
    a = np.zeros(n, dtype=np.float64)
    valid = ~nan_mask
    vals = flat[valid]
    # Clamp to stop range
    vmin, vmax = stops[0][0], stops[-1][0]
    vals = np.clip(vals, vmin, vmax)
    rv = np.empty_like(vals)
    gv = np.empty_like(vals)
    bv = np.empty_like(vals)
    av = np.empty_like(vals)
    # Initialize to last stop color
    rv[:] = stops[-1][1]; gv[:] = stops[-1][2]; bv[:] = stops[-1][3]; av[:] = stops[-1][4]
    # Tiered: each band gets the LOWER stop's flat color (no interpolation)
    for i in range(len(stops) - 1):
        lo = stops[i]
        hi = stops[i + 1]
        if i < len(stops) - 2:
            mask = (vals >= lo[0]) & (vals < hi[0])
        else:
            # Last band includes the upper bound
            mask = (vals >= lo[0]) & (vals <= hi[0])
        if not np.any(mask):
            continue
        rv[mask] = lo[1]
        gv[mask] = lo[2]
        bv[mask] = lo[3]
        av[mask] = lo[4]
    r[valid] = rv; g[valid] = gv; b[valid] = bv; a[valid] = av
    # Interleave RGBA
    rgba = np.zeros(n * 4, dtype=np.uint8)
    rgba[0::4] = np.clip(r, 0, 255).astype(np.uint8)
    rgba[1::4] = np.clip(g, 0, 255).astype(np.uint8)
    rgba[2::4] = np.clip(b, 0, 255).astype(np.uint8)
    rgba[3::4] = np.clip(a, 0, 255).astype(np.uint8)
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
        elif variable in ("thermal_updraft", "soaring_quality"):
            from app.services.soaring_derivation import (
                compute_wstar,
                compute_wstar_cape_fallback,
                compute_soaring_quality,
            )

            # Fetch auxiliary fields from same Herbie object
            def _safe_fetch(key: str) -> np.ndarray | None:
                try:
                    _ds = H.xarray(vdef[key])
                    return _ds[list(_ds.data_vars)[0]].values
                except Exception:
                    return None

            blh_arr = _safe_fetch("search_blh")
            t2m_arr = _safe_fetch("search_t2m")
            td2m_arr = _safe_fetch("search_td2m")
            tcdc_arr = _safe_fetch("search_tcdc")
            cape_arr = _safe_fetch("search_cape")

            shtfl = np.maximum(arr, 0.0)
            shtfl_ok = float(np.nanmax(shtfl)) > 0.01

            # Defaults for missing fields
            if t2m_arr is None:
                t2m_arr = np.full_like(shtfl, 288.0)
            if td2m_arr is None:
                td2m_arr = t2m_arr - 10.0  # assume 10K dewpoint depression
            if tcdc_arr is None:
                tcdc_arr = np.zeros_like(shtfl)
            if blh_arr is None:
                blh_arr = np.full_like(shtfl, 1000.0)

            if shtfl_ok:
                wstar = compute_wstar(shtfl, blh_arr, t2m_arr, td2m_arr, tcdc_arr)
            elif cape_arr is not None:
                wstar = compute_wstar_cape_fallback(cape_arr, blh_arr, t2m_arr, td2m_arr, tcdc_arr)
            else:
                wstar = np.zeros_like(shtfl)

            if variable == "soaring_quality":
                # Also need surface wind for composite
                wind_sfc = None
                if "search_wind_u" in vdef:
                    u_arr = _safe_fetch("search_wind_u")
                    v_arr = _safe_fetch("search_wind_v")
                    if u_arr is not None and v_arr is not None:
                        wind_sfc = np.sqrt(u_arr ** 2 + v_arr ** 2)
                arr = compute_soaring_quality(wstar, blh_arr, tcdc_arr, wind_sfc)
            else:
                arr = wstar
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

        # Corners from actual grid corners (after subsample)
        w_lon = float(lons_sub[0, 0])
        e_lon = float(lons_sub[0, -1])
        n_lat = float(lats_sub[0, 0])
        s_lat = float(lats_sub[-1, 0])
        # Detect if rows are south-to-north (first row has smaller lat)
        if lats_sub[0, 0] < lats_sub[-1, 0]:
            data_sub = np.flipud(data_sub)
            lats_sub = np.flipud(lats_sub)
            n_lat = float(lats_sub[0, 0])
            s_lat = float(lats_sub[-1, 0])
            # Recompute corner lons after flip (same columns, just rows flipped)
            w_lon = float(lons_sub[-1, 0])
            e_lon = float(lons_sub[-1, -1])
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

        n_lat = float(lats_1d.max())
        s_lat = float(lats_1d.min())
        w_lon = float(lons_1d.min())
        e_lon = float(lons_1d.max())

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

    # --- Debug value labels: sparse grid of text values for sanity check ---
    debug_labels: list[dict] = []
    label_step = max(1, min(height_px, width_px) // 8)  # ~8x8 grid of labels
    for r in range(0, height_px, label_step):
        for c in range(0, width_px, label_step):
            val = float(data_sub[r, c]) if not np.isnan(data_sub[r, c]) else None
            if val is None:
                continue
            if is_2d:
                lat_v = float(lats_sub[r, c])
                lon_v = float(lons_sub[r, c])
            else:
                lat_v = float(lats_1d[r]) if r < len(lats_1d) else None
                lon_v = float(lons_1d[c]) if c < len(lons_1d) else None
            if lat_v is not None and lon_v is not None:
                debug_labels.append({
                    "lat": round(lat_v, 2),
                    "lon": round(lon_v, 2),
                    "val": round(val, 3),
                })

    # MapLibre image source coordinates: [[w,n],[e,n],[e,s],[w,s]]
    coordinates = [
        [round(w_lon, 4), round(n_lat, 4)],
        [round(e_lon, 4), round(n_lat, 4)],
        [round(e_lon, 4), round(s_lat, 4)],
        [round(w_lon, 4), round(s_lat, 4)],
    ]

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
        "debug_labels": debug_labels,
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


def _fetch_grid(model: str, run_date: str, run_hour: str, fxx: int, variable: str) -> dict:
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

    step = SUBSAMPLE.get(model, 10)

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
    else:
        try:
            ds = H.xarray(vdef["search"])
        except Exception as exc:
            raise RuntimeError(f"Herbie xarray failed: {exc}")

        var_names = list(ds.data_vars)
        if not var_names:
            raise RuntimeError("No data variable in dataset")

        arr = ds[var_names[0]].values

        # Unit conversions so frontend gets display-ready values
        if variable == "vertical_velocity_700hPa":
            # Pa/s → m/s (positive = lift). At 700 hPa, ~−1 Pa/s ≈ +0.1 m/s
            arr = -arr / 10.0
        elif variable in ("thermal_updraft", "soaring_quality"):
            from app.services.soaring_derivation import (
                compute_wstar,
                compute_wstar_cape_fallback,
                compute_soaring_quality,
            )

            def _safe_fetch_gj(key: str) -> np.ndarray | None:
                try:
                    _ds = H.xarray(vdef[key])
                    return _ds[list(_ds.data_vars)[0]].values
                except Exception:
                    return None

            blh_arr = _safe_fetch_gj("search_blh")
            t2m_arr = _safe_fetch_gj("search_t2m")
            td2m_arr = _safe_fetch_gj("search_td2m")
            tcdc_arr = _safe_fetch_gj("search_tcdc")
            cape_arr = _safe_fetch_gj("search_cape")

            shtfl = np.maximum(arr, 0.0)
            shtfl_ok = float(np.nanmax(shtfl)) > 0.01

            if t2m_arr is None:
                t2m_arr = np.full_like(shtfl, 288.0)
            if td2m_arr is None:
                td2m_arr = t2m_arr - 10.0
            if tcdc_arr is None:
                tcdc_arr = np.zeros_like(shtfl)
            if blh_arr is None:
                blh_arr = np.full_like(shtfl, 1000.0)

            if shtfl_ok:
                wstar = compute_wstar(shtfl, blh_arr, t2m_arr, td2m_arr, tcdc_arr)
            elif cape_arr is not None:
                wstar = compute_wstar_cape_fallback(cape_arr, blh_arr, t2m_arr, td2m_arr, tcdc_arr)
            else:
                wstar = np.zeros_like(shtfl)

            if variable == "soaring_quality":
                wind_sfc = None
                if "search_wind_u" in vdef:
                    u_arr = _safe_fetch_gj("search_wind_u")
                    v_arr = _safe_fetch_gj("search_wind_v")
                    if u_arr is not None and v_arr is not None:
                        wind_sfc = np.sqrt(u_arr ** 2 + v_arr ** 2)
                arr = compute_soaring_quality(wstar, blh_arr, tcdc_arr, wind_sfc)
            else:
                arr = wstar

        lats = ds.latitude.values
        lons = ds.longitude.values
        features = _build_geojson(lats, lons, arr, step)

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "model": model,
            "variable": variable,
            "run": f"{run_date}T{run_hour}:00Z",
            "fxx": fxx,
        },
    }


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
):
    """Fetch a model grid via Herbie and return subsampled GeoJSON."""
    if model not in MODEL_CONFIG:
        raise HTTPException(400, f"Unknown model: {model}")
    if variable not in VARIABLES:
        raise HTTPException(400, f"Unknown variable: {variable}")
    if model in VARIABLES[variable].get("exclude_models", []):
        raise HTTPException(400, f"Variable {variable} not available for {model}")

    cache_key = f"{model}:{date}:{hour}:{fh}:{variable}"
    now = time.time()

    if cache_key in _grid_cache:
        data, ts = _grid_cache[cache_key]
        if now - ts < GRID_TTL:
            return JSONResponse(data)

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor, _fetch_grid, model, date, hour, fh, variable
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Unexpected error: {exc}")

    _grid_cache[cache_key] = (result, now)

    # Prune old cache entries
    for k, (_, ts) in list(_grid_cache.items()):
        if now - ts > GRID_TTL:
            del _grid_cache[k]

    return JSONResponse(result)


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

    cache_key = f"raster:{model}:{date}:{hour}:{fh}:{variable}"
    now = time.time()

    if cache_key in _raster_cache:
        data, ts = _raster_cache[cache_key]
        if now - ts < GRID_TTL:
            return JSONResponse(data)

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor, _fetch_raster, model, date, hour, fh, variable
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Unexpected error: {exc}")

    _raster_cache[cache_key] = (result, now)

    # Prune stale raster cache entries
    for k, (_, ts) in list(_raster_cache.items()):
        if now - ts > GRID_TTL:
            del _raster_cache[k]

    return JSONResponse(result)


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
