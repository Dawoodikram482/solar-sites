import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, pvgis
from app.main import app


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    """Every test gets an empty database and empty PVGIS caches."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    pvgis._production_cached.cache_clear()
    pvgis._hourly_cached.cache_clear()
    db.init_db()


def make_client() -> TestClient:
    return TestClient(app)


def register(client: TestClient, email="ann@example.com", password="correct horse") -> str:
    """Register and return the CSRF token."""
    r = client.post("/api/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["csrfToken"]


SITE = {
    "clientName": "Jansen",
    "address": "Lange Voorhout 1, Den Haag",
    "latitude": 52.08,
    "longitude": 4.31,
    "roofAreaM2": 30,
    "peakKwp": 5,
}


# --- Fake PVGIS -------------------------------------------------------------

FAKE_PVCALC = {
    "outputs": {
        "monthly": {"fixed": [{"month": m, "E_m": 100.0 * m} for m in range(1, 13)]},
        "totals": {"fixed": {"E_y": 7800.0}},
    }
}


def fake_hourly() -> dict:
    """A simple sun: 1000 W from 10:00 to 15:59 UTC every day, else nothing."""
    hours = [{"time": f"x:{i % 24:02d}10", "P": 1000.0 if 10 <= i % 24 < 16 else 0.0} for i in range(8760)]
    return {"outputs": {"hourly": hours}}


@pytest.fixture
def fake_pvgis(monkeypatch):
    """Replace httpx.get inside pvgis.py; record the calls that were made."""
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params))
        request = httpx.Request("GET", url)
        if url.endswith("PVcalc"):
            return httpx.Response(200, json=FAKE_PVCALC, request=request)
        return httpx.Response(200, json=fake_hourly(), request=request)

    monkeypatch.setattr(pvgis.httpx, "get", fake_get)
    return calls
