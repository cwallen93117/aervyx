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


@router.get("/variables")
async def weather_variables():
    """List available overlay variables."""
    return JSONResponse({
        "variables": [
            {"id": k, "is_wind_speed": v.get("is_wind_speed", False)}
            for k, v in VARIABLES.items()
        ]
    })
