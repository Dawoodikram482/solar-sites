"""Client for the European Commission's PVGIS API.

The browser never talks to PVGIS: all calls go through here (assignment rule).
That also lets us validate input, translate PVGIS errors into clear messages,
and cache answers.

Assumptions we send to PVGIS (the site has no tilt/orientation fields):
  - optimalangles=1: PVGIS picks the best tilt and orientation for the spot.
    Real roofs are often worse, so this is an upper-end estimate.
  - loss=14: 14 % system losses (cables, inverter, dirt), PVGIS's own default.
"""

import os
from functools import lru_cache

import httpx

BASE_URL = os.environ.get("PVGIS_BASE_URL", "https://re.jrc.ec.europa.eu/api/v5_3")
SYSTEM_LOSS_PERCENT = 14
# One fixed year for the hourly simulation. 2023 is the latest year in
# PVGIS 5.3's hourly data (and not a leap year: exactly 8760 hours).
HOURLY_YEAR = 2023
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class PvgisNoData(Exception):
    """PVGIS answered, but has no data for this location (e.g. over the sea)."""


class PvgisUnavailable(Exception):
    """PVGIS could not be reached, timed out, or sent something unexpected."""


def _get(endpoint: str, params: dict) -> dict:
    params = {**params, "outputformat": "json"}
    try:
        response = httpx.get(f"{BASE_URL}/{endpoint}", params=params, timeout=TIMEOUT)
    except httpx.HTTPError as exc:  # DNS failure, refused connection, timeout...
        raise PvgisUnavailable(f"Could not reach PVGIS ({exc.__class__.__name__})") from exc

    if response.status_code == 429 or response.status_code >= 500:
        raise PvgisUnavailable(f"PVGIS is busy or down (HTTP {response.status_code})")
    if response.status_code >= 400:
        # PVGIS answers 400 with {"message": "..."} for locations it has no
        # data for, such as "Location over the sea. Please, select another location".
        try:
            message = response.json().get("message", "")
        except ValueError:
            message = ""
        raise PvgisNoData(message or "PVGIS has no data for this location")
    try:
        return response.json()
    except ValueError as exc:
        raise PvgisUnavailable("PVGIS sent a response that is not valid JSON") from exc


# lru_cache: the same site asked twice does not cost a second PVGIS call.
# Exceptions are never cached, so a failed call is retried next time.
# Coordinates are rounded to 4 decimals (~10 m) before they reach the cache.
@lru_cache(maxsize=256)
def _production_cached(lat: float, lon: float, peak_kwp: float) -> dict:
    data = _get(
        "PVcalc",
        {"lat": lat, "lon": lon, "peakpower": peak_kwp, "loss": SYSTEM_LOSS_PERCENT, "optimalangles": 1},
    )
    try:
        outputs = data["outputs"]
        monthly = [
            {"month": int(m["month"]), "kwh": round(float(m["E_m"]), 1)}
            for m in outputs["monthly"]["fixed"]
        ]
        yearly = round(float(outputs["totals"]["fixed"]["E_y"]), 1)
    except (KeyError, TypeError, ValueError) as exc:
        raise PvgisUnavailable("PVGIS response did not have the expected shape") from exc
    if len(monthly) != 12:
        raise PvgisUnavailable("PVGIS did not return 12 months")
    return {"yearlyKwh": yearly, "monthlyKwh": monthly}


def get_production(lat: float, lon: float, peak_kwp: float) -> dict:
    """Average yearly and monthly production in kWh (PVGIS multi-year average)."""
    return _production_cached(round(lat, 4), round(lon, 4), peak_kwp)


@lru_cache(maxsize=64)
def _hourly_cached(lat: float, lon: float, peak_kwp: float) -> tuple[float, ...]:
    data = _get(
        "seriescalc",
        {
            "lat": lat,
            "lon": lon,
            "peakpower": peak_kwp,
            "loss": SYSTEM_LOSS_PERCENT,
            "optimalangles": 1,
            "pvcalculation": 1,
            "startyear": HOURLY_YEAR,
            "endyear": HOURLY_YEAR,
        },
    )
    try:
        # Each entry is one hour; "P" is the average PV power in watts during
        # that hour, so P / 1000 is the energy in kWh produced in that hour.
        hours = tuple(float(h["P"]) / 1000 for h in data["outputs"]["hourly"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PvgisUnavailable("PVGIS response did not have the expected shape") from exc
    if len(hours) != 8760:
        raise PvgisUnavailable(f"Expected 8760 hours from PVGIS, got {len(hours)}")
    return hours


def get_hourly_production(lat: float, lon: float, peak_kwp: float) -> tuple[float, ...]:
    """Production in kWh for each of the 8760 hours of HOURLY_YEAR."""
    return _hourly_cached(round(lat, 4), round(lon, 4), peak_kwp)
