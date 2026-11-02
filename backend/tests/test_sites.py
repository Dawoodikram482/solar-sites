import httpx

from app import pvgis
from conftest import SITE, make_client, register


def logged_in(email="ann@example.com"):
    client = make_client()
    csrf = register(client, email=email)
    client.headers["X-CSRF-Token"] = csrf
    return client


def test_crud_flow():
    c = logged_in()
    r = c.post("/api/sites", json=SITE)
    assert r.status_code == 201
    site = r.json()
    assert site == {"id": site["id"], **SITE}

    assert c.get("/api/sites").json() == [site]
    assert c.get(f"/api/sites/{site['id']}").json() == site

    changed = {**SITE, "clientName": "De Vries", "peakKwp": 6.5}
    r = c.put(f"/api/sites/{site['id']}", json=changed)
    assert r.status_code == 200
    assert r.json()["clientName"] == "De Vries"
    assert r.json()["peakKwp"] == 6.5

    assert c.delete(f"/api/sites/{site['id']}").status_code == 204
    assert c.get(f"/api/sites/{site['id']}").status_code == 404
    assert c.get("/api/sites").json() == []


def test_roof_area_is_optional():
    c = logged_in()
    body = {k: v for k, v in SITE.items() if k != "roofAreaM2"}
    r = c.post("/api/sites", json=body)
    assert r.status_code == 201
    assert r.json()["roofAreaM2"] is None


def test_sites_require_login():
    c = make_client()
    assert c.get("/api/sites").status_code == 401
    assert c.post("/api/sites", json=SITE).status_code == 401


def test_create_without_csrf_is_403():
    c = make_client()
    register(c)
    assert c.post("/api/sites", json=SITE).status_code == 403


def test_validation_message_per_field():
    c = logged_in()
    bad = {"clientName": "   ", "address": "x", "latitude": 100, "longitude": "east", "peakKwp": 0, "roofAreaM2": -1}
    r = c.post("/api/sites", json=bad)
    assert r.status_code == 422
    errors = r.json()["errors"]
    assert set(errors) == {"clientName", "latitude", "longitude", "peakKwp", "roofAreaM2"}
    assert all(isinstance(m, str) and m for m in errors.values())


def test_missing_fields_are_reported():
    r = logged_in().post("/api/sites", json={})
    assert r.status_code == 422
    assert {"clientName", "address", "latitude", "longitude", "peakKwp"} <= set(r.json()["errors"])


def test_advisors_only_see_their_own_sites(fake_pvgis):
    ann, bob = logged_in("ann@example.com"), logged_in("bob@example.com")
    site_id = ann.post("/api/sites", json=SITE).json()["id"]

    assert bob.get("/api/sites").json() == []
    assert bob.get(f"/api/sites/{site_id}").status_code == 404
    assert bob.put(f"/api/sites/{site_id}", json=SITE).status_code == 404
    assert bob.delete(f"/api/sites/{site_id}").status_code == 404
    assert bob.get(f"/api/sites/{site_id}/production").status_code == 404
    assert bob.get(f"/api/sites/{site_id}/battery?capacityKwh=5").status_code == 404
    # And Ann's site is untouched.
    assert ann.get(f"/api/sites/{site_id}").json()["clientName"] == "Jansen"


def test_user_id_in_body_is_ignored():
    ann, bob = logged_in("ann@example.com"), logged_in("bob@example.com")
    bob.post("/api/sites", json={**SITE, "userId": 1, "user_id": 1})
    assert ann.get("/api/sites").json() == []


def test_production(fake_pvgis):
    c = logged_in()
    site_id = c.post("/api/sites", json=SITE).json()["id"]
    r = c.get(f"/api/sites/{site_id}/production")
    assert r.status_code == 200
    body = r.json()
    assert body["yearlyKwh"] == 7800.0
    assert body["monthlyKwh"][0] == {"month": 1, "kwh": 100.0}
    assert len(body["monthlyKwh"]) == 12
    # The backend called PVGIS with the site's values.
    url, params = fake_pvgis[0]
    assert url.endswith("/PVcalc")
    assert params["lat"] == 52.08 and params["peakpower"] == 5
    # A second request is served from the cache.
    c.get(f"/api/sites/{site_id}/production")
    assert len(fake_pvgis) == 1


def test_production_no_data_is_clear_422(monkeypatch):
    def sea(url, params, timeout):
        return httpx.Response(400, json={"message": "Location over the sea. Please, select another location", "status": 400},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(pvgis.httpx, "get", sea)
    c = logged_in()
    site_id = c.post("/api/sites", json={**SITE, "latitude": 53.5, "longitude": 3.0}).json()["id"]
    r = c.get(f"/api/sites/{site_id}/production")
    assert r.status_code == 422
    assert "over the sea" in r.json()["detail"]


def test_production_pvgis_down_is_502(monkeypatch):
    def down(url, params, timeout):
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(pvgis.httpx, "get", down)
    c = logged_in()
    site_id = c.post("/api/sites", json=SITE).json()["id"]
    assert c.get(f"/api/sites/{site_id}/production").status_code == 502


def test_battery_endpoint(fake_pvgis):
    c = logged_in()
    site_id = c.post("/api/sites", json=SITE).json()["id"]
    r = c.get(f"/api/sites/{site_id}/battery?capacityKwh=10&annualUseKwh=3500")
    assert r.status_code == 200
    body = r.json()
    assert body["productionKwh"] == 6 * 365  # 1 kWh for 6 hours a day
    assert body["consumptionKwh"] == 3500
    assert body["withBattery"]["selfUsedKwh"] > body["withoutBattery"]["selfUsedKwh"]
    assert body["batteryAddsKwh"] > 0


def test_battery_query_validation(fake_pvgis):
    c = logged_in()
    site_id = c.post("/api/sites", json=SITE).json()["id"]
    r = c.get(f"/api/sites/{site_id}/battery")
    assert r.status_code == 422 and "capacityKwh" in r.json()["errors"]
    r = c.get(f"/api/sites/{site_id}/battery?capacityKwh=-1&annualUseKwh=0")
    assert set(r.json()["errors"]) == {"capacityKwh", "annualUseKwh"}
    r = c.get(f"/api/sites/{site_id}/battery?capacityKwh=nan")
    assert r.status_code == 422
