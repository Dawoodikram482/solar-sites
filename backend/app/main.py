"""Entry point: builds the FastAPI app, wires the routes, serves the frontend.

One process serves both the API (/api/...) and the built React files (/).
Same origin for both means: no CORS configuration, and the session cookie
just works with SameSite=Lax.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, sites
from .db import init_db

# Where the built frontend is (frontend/dist, copied in by the Dockerfile).
STATIC_DIR = os.environ.get("STATIC_DIR", os.path.join(os.path.dirname(__file__), "..", "static"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # create tables on startup
    yield


app = FastAPI(
    title="Solar sites",
    lifespan=lifespan,
    # Interactive API docs at /api/docs (handy for reviewers).
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

app.include_router(auth.router)
app.include_router(sites.router)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """Turn Pydantic's error list into one message per field.

    Pydantic reports errors like {"loc": ["body", "latitude"], "msg": "..."}.
    The contract asks for "a message per field", so we answer:
        422 {"detail": "Some fields are invalid", "errors": {"latitude": "..."}}
    The frontend shows each message under its own input.
    """
    errors: dict[str, str] = {}
    for error in exc.errors():
        loc = [str(part) for part in error["loc"] if part not in ("body", "query", "path")]
        field = loc[0] if loc else "body"
        message = error["msg"].removeprefix("Value error, ")
        errors.setdefault(field, message)  # keep the first message per field
    return JSONResponse(status_code=422, content={"detail": "Some fields are invalid", "errors": errors})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Cheap browser-side hardening on every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"  # no MIME-type guessing
    response.headers["X-Frame-Options"] = "DENY"            # no embedding in iframes (clickjacking)
    response.headers["Referrer-Policy"] = "same-origin"
    if not request.url.path.startswith("/api/docs"):
        # Only load scripts/styles/etc. from our own origin: an injected
        # <script src="https://evil..."> would be refused by the browser.
        # (Skipped for /api/docs, which loads its UI from a CDN.)
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    return response


# Serve the built React app. Mounted last, so /api/... routes win.
# html=True serves index.html for "/". The app has no client-side routes,
# so no other fallback is needed.
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
