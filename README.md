# Solar sites

A small web app for Praeter advisors: manage client sites, see the estimated
solar production per site (from PVGIS), and see what a home battery adds.

## Run it

```bash
docker build -t solar .
docker run -p 8000:8000 solar
```

Open <http://localhost:8000> and create an account. The API docs are at
<http://localhost:8000/api/docs>.

The database is a SQLite file inside the container, so data is gone when the
container is removed. To keep it: `docker run -p 8000:8000 -v solar-data:/app/data solar`.

### Without Docker (development)

```bash
# Backend (Python 3.12+), terminal 1
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# Frontend (Node 20.19+ or 22.12+), terminal 2
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to port 8000
```

### Tests

```bash
cd backend && pytest
```

31 tests cover registration and login, CSRF, logout, "advisors only see their
own sites", validation messages, PVGIS error handling (PVGIS is faked in the
tests), and the battery simulation.

## Project layout

```
Dockerfile              two stages: build React with Node, run everything with Python
backend/app/
  main.py               creates the app, validation-error format, security headers, serves the frontend
  db.py                 SQLite connection and schema (plain SQL)
  security.py           password hashing (scrypt) and session tokens
  schemas.py            request bodies and their validation rules (Pydantic)
  auth.py               register / login / logout / me, session + CSRF check
  sites.py              site CRUD, production and battery routes
  pvgis.py              the only code that talks to PVGIS
  battery.py            household consumption model + hour-by-hour battery simulation
backend/tests/          pytest tests
frontend/src/
  api.ts                every call to the backend (cookie, CSRF header, errors)
  types.ts              TypeScript types of the API data
  App.tsx               logged in or not?
  components/           AuthForm, SitesPage, SiteForm, SiteDetail
```

## Choices

**FastAPI (backend framework).** Request bodies are declared as typed classes
and validated automatically, which gives the "message per field" errors almost
for free. It also generates API docs. Lighter than Django for an app of this size.

**SQLite with plain SQL, no ORM.** No database server to run, so the whole app
is one container and one command. Plain `sqlite3` comes with Python; the schema
is three tables and every query is visible in the code. All queries use
parameters (`?`), never string formatting, so there is no SQL injection. For
several app servers or heavy concurrent writing I would switch to PostgreSQL.

**Vite + React + TypeScript, no extra libraries.** Vite is the standard,
officially recommended build tool for new React projects: TypeScript works with
almost no configuration, the dev server reloads instantly, and `npm run build`
outputs plain static files that FastAPI can serve. Only React itself. No router
(two screens, chosen by one piece of state), no state library, no UI kit, no
chart library (the monthly chart is CSS bars). Fewer moving parts, less to go
wrong. FastAPI serves the built files, so frontend and API share one origin:
no CORS setup needed.

**Sessions: HttpOnly cookie + CSRF token.**
- The session token is in an `HttpOnly` cookie, so JavaScript (including an
  injected script) cannot read it. A token in `localStorage` could be stolen by XSS.
- Because browsers send cookies automatically, cookies need CSRF protection:
  `SameSite=Lax`, plus a CSRF token that the API returns as `csrfToken` and
  expects in the `X-CSRF-Token` header on POST/PUT/DELETE (as the contract
  describes). `GET /api/me` also returns `csrfToken`, so the frontend gets it
  back after a page reload; it is kept in memory only.
- The database stores a SHA-256 hash of the session token, not the token.
  Logout deletes the session server-side. Sessions expire after 7 days.
- The cookie is not `Secure` by default because the assessment runs on plain
  `http://localhost`. Set `COOKIE_SECURE=1` behind HTTPS.

**Passwords: scrypt** from Python's standard library, with a random salt per
password. Login gives the same answer and takes the same time for "unknown
email" and "wrong password".

**Other safety measures:** every site query filters on the logged-in user's id
(the user id never comes from the request); another advisor's site gives 404,
not 403, so ids of other advisors' sites are not confirmed; security headers
(Content-Security-Policy, X-Frame-Options, nosniff); the container runs as a
non-root user.

### HTTP status codes

| Situation | Code |
|---|---|
| Register OK / site created | 201 Created |
| Logout, delete | 204 No Content |
| Invalid input (body or query) | 422, with `{"detail", "errors": {field: message}}` |
| Email already registered | 409 Conflict |
| Wrong credentials, no or expired session | 401 Unauthorized |
| Logged in but missing/wrong CSRF token | 403 Forbidden |
| Site does not exist or is not yours | 404 Not Found |
| PVGIS has no data for the location (e.g. at sea) | 422, with PVGIS's reason |
| PVGIS unreachable, timed out or garbled | 502 Bad Gateway |

### PVGIS

All PVGIS calls go through the backend (`pvgis.py`).

- A site has no tilt or orientation, so we ask PVGIS for the **optimal angles**
  (`optimalangles=1`) and its standard **14 % system losses**. Real roofs are
  often less ideal, so the estimate is on the optimistic side.
- **Production** uses `PVcalc` (long-term average per month and year).
- **Battery** uses `seriescalc` for the hourly production of one real year
  (2023). That year's total differs a little from the long-term average,
  which is why the battery answer reports its own `productionKwh`.
- Answers are cached in memory (per coordinates + kWp), so the same site does
  not hit PVGIS twice. Failed calls are not cached.
- The roof area is stored but not used in the calculation: PVGIS needs the
  panel capacity (kWp), and that already says how big the installation is.
  The roof area is useful information for the advisor (does the system fit?).

### The household consumption assumption

PVGIS has no consumption data. The advisor enters the client's **yearly use in
kWh** (`annualUseKwh`, on every energy bill; default 3000 when left out). The
backend spreads it over the 8760 hours of the year with:

- a fixed **daily shape**: low at night, a morning bump, a large evening peak;
- a **monthly factor**: about 20–25 % more in winter months than average, about
  15 % less in summer.

The profile is a simplified, hand-made approximation of a typical Dutch
household, scaled so the year adds up exactly to the entered yearly use.
**Why:** what decides self-consumption is *when* electricity is used compared
to when the sun shines; this shape captures the essential fact that most use
is in the evening, when there is no sun. It needs only one input the advisor
can actually get. **Better:** the official NEDU standard profiles, or the
client's own smart-meter data.

PVGIS timestamps are UTC; the profile assumes Dutch time as UTC+1 all year
(daylight saving time is ignored, which barely changes yearly totals).

This profile describes a Dutch household (Dutch clock time, more use in winter).
The production estimate works for any location PVGIS covers, but the battery
result is only meaningful for sites in the Netherlands: elsewhere the time zone
and seasonal pattern would be wrong (e.g. Pakistan is UTC+5 and uses most
electricity in summer, for air conditioning).

### The battery simulation

Hour by hour through the year (`battery.py`):

1. Solar goes to the house first.
2. Surplus charges the battery; whatever does not fit is exported.
3. Shortfall is covered from the battery; the rest is imported.

Assumptions: 90 % round-trip efficiency (all losses booked when charging), a
maximum charge/discharge power of 0.5 × capacity per hour (a 10 kWh battery
does 5 kW), starts empty on 1 January. "Without battery" is the same
simulation with capacity 0, so both cases always use identical logic.

`GET /api/sites/{id}/battery` returns `productionKwh`, `consumptionKwh`, and for
`withoutBattery` and `withBattery`: `selfUsedKwh`, `gridImportKwh`,
`gridExportKwh`, `selfConsumptionPercent` (share of solar used at home) and
`selfSufficiencyPercent` (share of use covered by solar), plus `batteryAddsKwh`.

## What I would do next

- Rate-limit login and registration (brute force protection).
- Let advisors enter roof tilt and orientation instead of assuming optimal angles.
- Use NEDU profiles or smart-meter data for consumption; model daylight saving time.
- Show the money: savings per year with the current energy prices and feed-in compensation.
- Store PVGIS answers in the database instead of memory, so they survive restarts.
- Frontend tests (e.g. Vitest + Testing Library) and an end-to-end test.
- PostgreSQL and migrations (e.g. Alembic) if the app grows.
