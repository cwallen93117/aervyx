from __future__ import annotations
import io, math
from datetime import datetime, timedelta, timezone
import httpx, numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/weather", tags=["weather"])
NOMADS_BASE = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rap/prod"

VARIABLE_MAP = {
    "cape":                    {"shortName": "cape", "typeOfLevel": "surface",           "level": 0,   "unit": "J/kg"},
    "boundary_layer_height":   {"shortName": "hpbl", "typeOfLevel": "surface",           "level": 0,   "unit": "m"},
    "lifted_index":            {"shortName": "lftx", "typeOfLevel": "surface",           "level": 0,   "unit": ""},
    "cloud_cover":             {"shortName": "tcc",  "typeOfLevel": "atmosphere",        "level": 0,   "unit": "%"},
    "precipitation":           {"shortName": "tp",   "typeOfLevel": "surface",           "level": 0,   "unit": "mm"},
    "convective_cloud_top":    {"shortName": "ct",   "typeOfLevel": "convectiveCloudTop","level": 0,   "unit": "m"},
    "convective_cloud_base":   {"shortName": "cb",   "typeOfLevel": "convectiveCloudBase","level": 0,  "unit": "m"},
    "wind_u_component_10m":    {"shortName": "u",    "typeOfLevel": "heightAboveGround", "level": 10,  "unit": "m/s"},
    "wind_v_component_10m":    {"shortName": "v",    "typeOfLevel": "heightAboveGround", "level": 10,  "unit": "m/s"},
    "wind_u_component_850hPa": {"shortName": "u",    "typeOfLevel": "isobaricInhPa",     "level": 850, "unit": "m/s"},
    "wind_v_component_850hPa": {"shortName": "v",    "typeOfLevel": "isobaricInhPa",     "level": 850, "unit": "m/s"},
    "wind_u_component_700hPa": {"shortName": "u",    "typeOfLevel": "isobaricInhPa",     "level": 700, "unit": "m/s"},
    "wind_v_component_700hPa": {"shortName": "v",    "typeOfLevel": "isobaricInhPa",     "level": 700, "unit": "m/s"},
    "wind_u_component_500hPa": {"shortName": "u",    "typeOfLevel": "isobaricInhPa",     "level": 500, "unit": "m/s"},
    "wind_v_component_500hPa": {"shortName": "v",    "typeOfLevel": "isobaricInhPa",     "level": 500, "unit": "m/s"},
}

def _latest_cycle():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d"), max(0, now.hour - 2)

@router.get("/rap/available")
async def rap_available():
    date_str, cycle = _latest_cycle()
    max_fh = 51 if cycle in (0, 6, 12, 18) else 18
    base = datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]), cycle, 0, 0, tzinfo=timezone.utc)
    valid_times = [(base + timedelta(hours=fh)).strftime("%Y-%m-%dT%H:%MZ") for fh in range(max_fh + 1)]
    return JSONResponse({"model": "rap", "label": "RAP 13km", "reference_time": f"{date_str}T{cycle:02d}:00Z", "valid_times": valid_times, "variables": list(VARIABLE_MAP.keys())})

@router.get("/rap/grid")
async def rap_grid(
    variable: str = Query(...),
    valid_time: str = Query(...),
    west: float = Query(-130.0), east: float = Query(-60.0),
    south: float = Query(20.0),  north: float = Query(55.0),
):
    if variable not in VARIABLE_MAP:
        raise HTTPException(400, f"Unknown variable '{variable}'")
    try:
        import cfgrib
    except ImportError:
        raise HTTPException(503, "cfgrib not installed — RAP proxy unavailable")
    try:
        vt = datetime.strptime(valid_time.rstrip("Z") + "+00:00", "%Y-%m-%dT%H:%M%z")
    except ValueError:
        raise HTTPException(400, "valid_time must be YYYY-MM-DDTHH:MMZ")
    date_str, cycle = _latest_cycle()
    base = datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]), cycle, 0, 0, tzinfo=timezone.utc)
    fhour = max(0, min(51, round((vt - base).total_seconds() / 3600)))
    url = f"{NOMADS_BASE}/rap.{date_str}/rap.t{cycle:02d}z.wrfnatf{fhour:02d}.grib2"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.get(url)
        if resp.status_code == 404:
            raise HTTPException(404, f"RAP file not available: {url}")
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"NOMADS fetch failed: {exc}")
    cfg = VARIABLE_MAP[variable]
    try:
        datasets = cfgrib.open_datasets(io.BytesIO(resp.content))
    except Exception as exc:
        raise HTTPException(500, f"GRIB2 parse error: {exc}")
    data_array = lats = lons = None
    for ds in datasets:
        if cfg["shortName"] not in ds.data_vars:
            continue
        da = ds[cfg["shortName"]]
        for dim in ("isobaricInhPa", "heightAboveGround"):
            if dim in da.dims and cfg["level"] != 0:
                try: da = da.sel({dim: cfg["level"]}); break
                except: pass
        data_array = da.values
        for n in ("latitude", "lat"):
            if n in ds.coords: lats = ds.coords[n].values; break
        for n in ("longitude", "lon"):
            if n in ds.coords: lons = ds.coords[n].values; break
        break
    if data_array is None:
        raise HTTPException(404, f"Variable '{variable}' not found in RAP output")
    if lons.max() > 180:
        lons = np.where(lons > 180, lons - 360, lons)
    ny, nx = data_array.shape
    stride = max(1, min(ny, nx) // 50)
    features = []
    for iy in range(0, ny, stride):
        for ix in range(0, nx, stride):
            lat = float(lats[iy] if lats.ndim == 1 else lats[iy, ix])
            lon = float(lons[ix] if lons.ndim == 1 else lons[iy, ix])
            if not (south <= lat <= north and west <= lon <= east): continue
            val = float(data_array[iy, ix])
            if math.isnan(val): continue
            features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 3), round(lat, 3)]}, "properties": {"value": round(val, 2), "unit": cfg["unit"]}})
    return JSONResponse({"type": "FeatureCollection", "features": features, "metadata": {"model": "rap", "variable": variable, "valid_time": valid_time, "count": len(features)}})
