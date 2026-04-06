"""Soaring weather derivation functions.

Pure numpy functions for computing soaring-relevant derived variables from
raw NWP model fields.  No Herbie or network dependencies — input/output are
plain numpy arrays, making the formulas easy to unit-test.

Key references:
  - Deardorff convective velocity scale (W*)
  - DrJack RASP parameter definitions (wstar, hbl, bsratio)
  - SoaringMeteo GFS pipeline derivation approach
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
G = 9.81          # gravitational acceleration  (m/s²)
RHO_CP = 1200.0   # ρ × cp for dry air at surface  (J / m³·K)
RD = 287.05        # specific gas constant for dry air  (J / kg·K)
EPS = 0.622        # Rd / Rv


# ---------------------------------------------------------------------------
# Helper: mixing ratio from dewpoint + surface pressure
# ---------------------------------------------------------------------------
def _saturation_vapor_pressure(t_k: np.ndarray) -> np.ndarray:
    """Bolton (1980) saturation vapor pressure  (Pa).

    t_k : temperature in Kelvin.
    """
    t_c = t_k - 273.15
    # Clamp to avoid log-domain issues at extreme cold
    t_c = np.clip(t_c, -80.0, 60.0)
    return 611.2 * np.exp(17.67 * t_c / (t_c + 243.5))


def mixing_ratio_from_dewpoint(
    td_k: np.ndarray,
    psfc_pa: float = 101325.0,
) -> np.ndarray:
    """Approximate mixing ratio (kg/kg) from dewpoint temperature (K).

    Uses a fixed surface pressure when pressure field is unavailable.
    """
    e = _saturation_vapor_pressure(td_k)
    return EPS * e / (psfc_pa - e)


# ---------------------------------------------------------------------------
# Core: Convective velocity scale W*
# ---------------------------------------------------------------------------
def compute_wstar(
    shtfl: np.ndarray,
    blh: np.ndarray,
    t2m: np.ndarray,
    td2m: np.ndarray,
    tcdc: np.ndarray,
) -> np.ndarray:
    """Compute W* (convective velocity scale) with moisture & cloud corrections.

    Parameters
    ----------
    shtfl : sensible heat flux at surface  (W/m²).  Positive = upward.
    blh   : boundary layer height  (m).
    t2m   : 2-metre temperature  (K).
    td2m  : 2-metre dewpoint temperature  (K).
    tcdc  : total cloud cover  (%, 0–100).

    Returns
    -------
    wstar : thermal updraft velocity estimate  (m/s).
    """
    # Sanitize inputs
    shtfl = np.maximum(np.asarray(shtfl, dtype=np.float64), 0.0)
    blh = np.maximum(np.asarray(blh, dtype=np.float64), 10.0)
    t2m = np.asarray(t2m, dtype=np.float64)
    td2m = np.asarray(td2m, dtype=np.float64)
    tcdc = np.clip(np.asarray(tcdc, dtype=np.float64), 0.0, 100.0)

    # --- Virtual temperature (accounts for moisture in buoyancy) ---
    w = mixing_ratio_from_dewpoint(td2m)
    t_virtual = t2m * (1.0 + 0.61 * w)
    # Floor virtual temp to avoid division by zero at extreme cold
    t_virtual = np.maximum(t_virtual, 200.0)

    # --- Base W* (Deardorff convective velocity scale) ---
    #   W* = [ (g / Tv) × zi × Hs / (ρ cp) ] ^ (1/3)
    # where Hs = sensible heat flux, zi = BLH
    wstar = np.power(
        (G / t_virtual) * blh * shtfl / RHO_CP,
        1.0 / 3.0,
    )

    # --- Moisture inhibition ---
    # Dewpoint depression: larger = drier BL = better thermals
    # DD < 5K → very moist, thermals strongly suppressed
    # DD > 15K → dry, no penalty
    dd = t2m - td2m
    moisture_factor = np.clip(dd / 15.0, 0.0, 1.0)
    wstar *= moisture_factor

    # --- Cloud cover suppression ---
    # Squared cloud fraction → scattered clouds barely penalize,
    # overcast kills thermals almost entirely.
    # The 0.8 coefficient preserves residual activity under broken cloud.
    cloud_frac = tcdc / 100.0
    cloud_factor = 1.0 - 0.8 * np.power(cloud_frac, 2.0)
    wstar *= cloud_factor

    return wstar


# ---------------------------------------------------------------------------
# Composite soaring quality index
# ---------------------------------------------------------------------------
def compute_soaring_quality(
    wstar: np.ndarray,
    blh: np.ndarray,
    tcdc: np.ndarray,
    wind_sfc: np.ndarray | None = None,
) -> np.ndarray:
    """Compute a composite soaring quality score (0–10 scale).

    Blends thermal strength, BL height, cloud cover, and surface wind
    into a single pilot-friendly metric.

    Parameters
    ----------
    wstar    : thermal updraft velocity  (m/s).
    blh      : boundary layer height  (m).
    tcdc     : total cloud cover  (%, 0–100).
    wind_sfc : surface wind speed  (m/s).  Optional — omitted → no wind penalty.

    Returns
    -------
    score : soaring quality  (0–10).
    """
    # Normalise each factor to 0–1
    # Thermal strength: 0 m/s → 0, ≥3 m/s → 1  (3 m/s ≈ 600 fpm, very good)
    f_thermal = np.clip(np.asarray(wstar, dtype=np.float64) / 3.0, 0.0, 1.0)

    # BL height: 0 m → 0, ≥3000 m → 1  (3000 m = great thermalling ceiling)
    f_blh = np.clip(np.asarray(blh, dtype=np.float64) / 3000.0, 0.0, 1.0)

    # Cloud cover: 0 % → 1, 100% → 0
    f_cloud = 1.0 - np.clip(np.asarray(tcdc, dtype=np.float64) / 100.0, 0.0, 1.0)

    # Wind: 0 m/s → 1, ≥15 m/s → 0  (strong wind is bad for launching/thermalling)
    if wind_sfc is not None:
        f_wind = 1.0 - np.clip(np.asarray(wind_sfc, dtype=np.float64) / 15.0, 0.0, 1.0)
    else:
        f_wind = 1.0

    # Weighted composite
    # Thermal strength dominates (0.45), then BL height (0.25),
    # cloud (0.20), wind (0.10)
    score = (
        0.45 * f_thermal
        + 0.25 * f_blh
        + 0.20 * f_cloud
        + 0.10 * f_wind
    )

    return score * 10.0  # scale to 0–10


# ---------------------------------------------------------------------------
# CAPE-based fallback W* (for when SHTFL is unavailable, e.g. fh=0)
# ---------------------------------------------------------------------------
def compute_wstar_cape_fallback(
    cape: np.ndarray,
    blh: np.ndarray,
    t2m: np.ndarray,
    td2m: np.ndarray,
    tcdc: np.ndarray,
) -> np.ndarray:
    """Estimate W* from CAPE + BLH when SHTFL is not available.

    Uses the relationship:  Hs_est ≈ (ρ cp / g) × CAPE × g / (2 × zi)
    which gives a rough surface heat flux proxy from CAPE and BL depth.
    Then feeds that into the standard W* with corrections.

    This is less accurate than the SHTFL path but much better than the
    old arbitrary coefficient approach.
    """
    cape = np.maximum(np.asarray(cape, dtype=np.float64), 0.0)
    blh = np.maximum(np.asarray(blh, dtype=np.float64), 10.0)
    t2m = np.asarray(t2m, dtype=np.float64)
    td2m = np.asarray(td2m, dtype=np.float64)
    tcdc = np.clip(np.asarray(tcdc, dtype=np.float64), 0.0, 100.0)

    # Virtual temperature
    w = mixing_ratio_from_dewpoint(td2m)
    t_virtual = np.maximum(t2m * (1.0 + 0.61 * w), 200.0)

    # Approximate W* from CAPE:
    # W* ≈ (CAPE × g / (Tv))^(1/3) × scaling_factor
    # The scaling_factor of 0.4 is calibrated to match SHTFL-based W*
    # for typical convective conditions.
    wstar = 0.4 * np.power(np.maximum(cape * G / t_virtual, 0.0), 1.0 / 3.0)

    # Cap at reasonable maximum
    wstar = np.minimum(wstar, 8.0)

    # Apply same moisture + cloud corrections
    dd = t2m - td2m
    moisture_factor = np.clip(dd / 15.0, 0.0, 1.0)
    wstar *= moisture_factor

    cloud_frac = tcdc / 100.0
    cloud_factor = 1.0 - 0.8 * np.power(cloud_frac, 2.0)
    wstar *= cloud_factor

    return wstar
