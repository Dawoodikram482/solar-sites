"""Client sites: CRUD plus the production and battery estimates.

Every route depends on `require_user`, and every SQL query filters on
`user_id = <the logged-in user>`. That filter is what makes "advisors only
see their own sites" true: there is no query in this file that can return or
change another user's row.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from . import pvgis
from .auth import require_user
from .battery import battery_report
from .db import get_db
from .schemas import SiteIn

router = APIRouter(prefix="/api/sites")


def site_to_json(row: sqlite3.Row) -> dict:
    """Database row (snake_case) -> API shape (camelCase). user_id is not exposed."""
    return {
        "id": row["id"],
        "clientName": row["client_name"],
        "address": row["address"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "roofAreaM2": row["roof_area_m2"],
        "peakKwp": row["peak_kwp"],
    }


def get_owned_site(db: sqlite3.Connection, site_id: int, user_id: int) -> sqlite3.Row:
    """Fetch a site only if it belongs to this user.

    A site that does not exist and a site of another advisor both give 404.
    Answering 403 for the second case would tell an attacker "this id exists,
    it's just not yours" — 404 leaks nothing.
    """
    row = db.execute(
        "SELECT * FROM sites WHERE id = ? AND user_id = ?", (site_id, user_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return row


@router.get("")
def list_sites(session=Depends(require_user), db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM sites WHERE user_id = ? ORDER BY id", (session["user_id"],)
    ).fetchall()
    return [site_to_json(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_site(body: SiteIn, session=Depends(require_user), db: sqlite3.Connection = Depends(get_db)):
    # user_id comes from the session, never from the request body.
    cursor = db.execute(
        """INSERT INTO sites (user_id, client_name, address, latitude, longitude, roof_area_m2, peak_kwp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session["user_id"], body.client_name, body.address, body.latitude,
         body.longitude, body.roof_area_m2, body.peak_kwp),
    )
    return site_to_json(get_owned_site(db, cursor.lastrowid, session["user_id"]))


@router.get("/{site_id}")
def get_site(site_id: int, session=Depends(require_user), db: sqlite3.Connection = Depends(get_db)):
    return site_to_json(get_owned_site(db, site_id, session["user_id"]))


@router.put("/{site_id}")
def update_site(site_id: int, body: SiteIn, session=Depends(require_user), db: sqlite3.Connection = Depends(get_db)):
    get_owned_site(db, site_id, session["user_id"])  # 404 unless it is ours
    # PUT replaces the whole site, so an omitted roofAreaM2 becomes empty.
    db.execute(
        """UPDATE sites SET client_name = ?, address = ?, latitude = ?, longitude = ?,
                            roof_area_m2 = ?, peak_kwp = ?
           WHERE id = ? AND user_id = ?""",
        (body.client_name, body.address, body.latitude, body.longitude,
         body.roof_area_m2, body.peak_kwp, site_id, session["user_id"]),
    )
    return site_to_json(get_owned_site(db, site_id, session["user_id"]))


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(site_id: int, session=Depends(require_user), db: sqlite3.Connection = Depends(get_db)):
    get_owned_site(db, site_id, session["user_id"])
    db.execute("DELETE FROM sites WHERE id = ? AND user_id = ?", (site_id, session["user_id"]))


def _call_pvgis(func, *args):
    """Run a PVGIS call and turn its errors into HTTP answers.

    - No data for the location -> 422: the request is understood, but this
      site's location cannot be calculated. The advisor can fix it (move the
      coordinates), so it is a client-side problem, not a server crash.
    - PVGIS down / timed out / garbled -> 502 Bad Gateway: our server works,
      the service behind it failed. Retrying later may help.
    """
    try:
        return func(*args)
    except pvgis.PvgisNoData as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"PVGIS has no solar data for this location: {exc}",
        )
    except pvgis.PvgisUnavailable as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"The solar data service (PVGIS) is unavailable, try again later. {exc}",
        )


@router.get("/{site_id}/production")
def production(site_id: int, session=Depends(require_user), db: sqlite3.Connection = Depends(get_db)):
    site = get_owned_site(db, site_id, session["user_id"])
    return _call_pvgis(pvgis.get_production, site["latitude"], site["longitude"], site["peak_kwp"])


@router.get("/{site_id}/battery")
def battery(
    site_id: int,
    capacity_kwh: float = Query(alias="capacityKwh", ge=0, le=200),
    # Default if not sent: a round, typical yearly use for a Dutch household.
    # The advisor should enter the client's real figure from the energy bill.
    annual_use_kwh: float = Query(3000, alias="annualUseKwh", gt=0, le=100_000),
    session=Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    site = get_owned_site(db, site_id, session["user_id"])
    hourly = _call_pvgis(pvgis.get_hourly_production, site["latitude"], site["longitude"], site["peak_kwp"])
    return battery_report(hourly, annual_use_kwh, capacity_kwh, pvgis.HOURLY_YEAR)
