from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/models")
async def weather_models():
    """List available weather models and their tile sources."""
    return JSONResponse({
        "models": [
            {"id": "ncep_hrrr_conus", "label": "HRRR", "resolution": "3km", "coverage": "CONUS", "source": "open-meteo"},
            {"id": "ncep_gfs025", "label": "GFS", "resolution": "25km", "coverage": "Global", "source": "open-meteo"},
            {"id": "dwd_icon", "label": "ICON", "resolution": "11km", "coverage": "Global", "source": "open-meteo"},
            {"id": "ncep_nam_conus", "label": "NAM", "resolution": "3km", "coverage": "CONUS", "source": "open-meteo"},
        ]
    })
