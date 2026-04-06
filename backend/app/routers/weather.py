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
    },
    "lifted_index": {
        "search": ":4LFTX:",
        "product_overrides": {},
    },
    "cloud_cover": {
        "search": ":TCDC:entire atmosphere:",
        "product_overrides": {},
    },
    "precipitation": {
        "search": ":APCP:surface:",
        "product_overrides": {},
    },
    "vertical_velocity_700hPa": {
        "search": ":VVEL:700 mb:",
        "product_overrides": {"hrrr": "prs"},
    },
    "convective_cloud_top": {
        "search": ":HGT:cloud top:",
        "product_overrides": {"hrrr": "prs"},
    },
    "convective_cloud_base": {
        "search": ":HGT:cloud base:",
        "product_overrides": {"hrrr": "prs"},
    },
    "wind_speed_10m": {
        "search": ":UGRD:10 m above ground:",
        "search_v": ":VGRD:10 m above ground:",
        "is_wind_speed": True,
        "product_overrides": {},
    },
    "wind_speed_850hPa": {
        "search": ":UGRD:850 mb:",
        "search_v": ":VGRD:850 mb:",
        "is_wind_speed": True,
        "product_overrides": {"hrrr": "prs"},
    },
    "wind_speed_700hPa": {
        "search": ":UGRD:700 mb:",
        "search_v": ":VGRD:700 mb:",
        "is_wind_speed": True,
        "product_overrides": {"hrrr": "prs"},
    },
    "wind_speed_500hPa": {
        "search": ":UGRD:500 mb:",
        "search_v": ":VGRD:500 mb:",
        "is_wind_speed": True,
        "product_overrides": {"hrrr": "prs"},
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
# Color scale definitions for soaring weather visualization
# Each entry: (value, R, G, B, A) — values are linearly interpolated
# ---------------------------------------------------------------------------
_COLOR_SCALES: dict[str, list[tuple[float, int, int, int, int]]] = {
    # thermal strength 0-5 m/s: transparent→blue→green→yellow→red
    "vertical_velocity_700hPa": [
        (0.0,  0,   0,   200, 20),
        (0.5,  0,   80,  220, 80),
        (1.5,  0,   200, 80,  150),
        (2.5,  80,  220, 0,   180),
        (3.5,  220, 200, 0,   200),
        (5.0,  220, 0,   0,   210),
    ],
    # CAPE 0-2000 J/kg: transparent→blue→green→yellow→red
    "cape": [
        (0.0,   0,   0,   180, 20),
        (100.0, 0,   60,  220, 80),
        (500.0, 0,   200, 60,  150),
        (1000.0,180, 220, 0,   190),
        (1500.0,220, 140, 0,   205),
        (2000.0,220, 0,   0,   215),
    ],
    # cloud top height 0-7000 m: gray→green→light blue→purple→magenta
    "convective_cloud_top": [
        (0.0,    100, 100, 100, 30),
        (1000.0, 60,  180, 60,  120),
        (2500.0, 80,  180, 220, 165),
        (4500.0, 140, 80,  200, 185),
        (7000.0, 220, 60,  200, 200),
    ],
    # boundary layer height 0-3500 m: gray→green→light blue→purple→magenta
    "boundary_layer_height": [
        (0.0,    100, 100, 100, 30),
        (500.0,  60,  180, 60,  120),
        (1500.0, 80,  180, 220, 165),
        (2500.0, 140, 80,  200, 185),
        (3500.0, 220, 60,  200, 200),
    ],
    # lifted index -8 to +4: red(unstable)→orange→green→blue(stable)
    "lifted_index": [
        (-8.0, 220, 0,   0,   210),
        (-4.0, 220, 120, 0,   195),
        (-1.0, 200, 200, 0,   170),
        (0.0,  60,  200, 60,  140),
        (2.0,  0,   120, 220, 100),
        (4.0,  0,   40,  200, 60),
    ],
    # cloud cover 0-100%: transparent→light gray→dark gray→near-black
    "cloud_cover": [
        (0.0,   220, 220, 220, 20),
        (20.0,  190, 190, 190, 80),
        (50.0,  140, 140, 140, 140),
        (80.0,  80,  80,  80,  185),
        (100.0, 30,  30,  30,  210),
    ],
    # precipitation 0-20 mm: transparent→light blue→blue→purple
    "precipitation": [
        (0.0,   120, 200, 240, 20),
        (1.0,   60,  140, 220, 100),
        (5.0,   20,  60,  200, 165),
        (10.0,  80,  20,  180, 190),
        (20.0,  120, 0,   140, 210),
    ],
    # wind 10m 0-30 m/s: green→yellow→orange→red
    "wind_speed_10m": [
        (0.0,   20,  180, 60,  30),
        (5.0,   60,  200, 60,  120),
        (10.0,  200, 220, 0,   165),
        (18.0,  220, 120, 0,   190),
        (24.0,  220, 40,  0,   205),
        (30.0,  200, 0,   0,   215),
    ],
    # wind 850 hPa 0-30 m/s: green→yellow→orange→red
    "wind_speed_850hPa": [
        (0.0,   20,  180, 60,  30),
        (5.0,   60,  200, 60,  120),
        (10.0,  200, 220, 0,   165),
        (18.0,  220, 120, 0,   190),
        (24.0,  220, 40,  0,   205),
        (30.0,  200, 0,   0,   215),
    ],
    # wind 700 hPa 0-40 m/s: green→yellow→orange→red
    "wind_speed_700hPa": [
        (0.0,   20,  180, 60,  30),
        (5.0,   60,  200, 60,  120),
        (15.0,  200, 220, 0,   165),
        (25.0,  220, 120, 0,   190),
        (32.0,  220, 40,  0,   205),
        (40.0,  200, 0,   0,   215),
    ],
    # wind 500 hPa 0-50 m/s: green→yellow→orange→red
    "wind_speed_500hPa": [
        (0.0,   20,  180, 60,  30),
        (8.0,   60,  200, 60,  120),
        (20.0,  200, 220, 0,   165),
        (32.0,  220, 120, 0,   190),
        (42.0,  220, 40,  0,   205),
        (50.0,  200, 0,   0,   215),
    ],
}


def _colorize_array(
    data: Any,
    stops: list[tuple[float, int, int, int, int]],
) -> bytes:
    """Vectorized: map a 2-D float array to RGBA bytes via color stops."""
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
    # Initialize to last stop
    rv[:] = stops[-1][1]; gv[:] = stops[-1][2]; bv[:] = stops[-1][3]; av[:] = stops[-1][4]
    for i in range(len(stops) - 1):
        lo = stops[i]
        hi = stops[i + 1]
        mask = (vals >= lo[0]) & (vals <= hi[0])
        if not np.any(mask):
            continue
        denom = hi[0] - lo[0]
        t = (vals[mask] - lo[0]) / denom if denom != 0 else np.zeros(mask.sum())
        rv[mask] = lo[1] + t * (hi[1] - lo[1])
        gv[mask] = lo[2] + t * (hi[2] - lo[2])
        bv[mask] = lo[3] + t * (hi[3] - lo[3])
        av[mask] = lo[4] + t * (hi[4] - lo[4])
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
        height_px = len(lats_1d)
        width_px = len(lons_1d)

        n_lat = float(lats_1d.max())
        s_lat = float(lats_1d.min())
        w_lon = float(lons_1d.min())
        e_lon = float(lons_1d.max())

        # Ensure first image row = northernmost lat
        if lats_1d[0] < lats_1d[-1]:
            data_sub = np.flipud(data_sub)

    # Retrieve color stops for this variable (fall back to a neutral gray scale)
    stops = _COLOR_SCALES.get(variable)
    if stops is None:
        vmin = float(np.nanmin(data_sub))
        vmax = float(np.nanmax(data_sub))
        vmax = vmax if vmax != vmin else vmin + 1
        stops = [
            (vmin, 200, 200, 200, 30),
            (vmax, 60, 60, 60, 200),
        ]

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

    return {
        "image": data_uri,
        "coordinates": coordinates,
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
            {"id": k, "is_wind_speed": v.get("is_wind_speed", False)}
            for k, v in VARIABLES.items()
        ]
    })
