"""Accounts and sessions: /api/register, /api/login, /api/logout, /api/me.

How a session works here
------------------------
1. On register/login we create a random session token and a random CSRF token.
2. The session token goes to the browser in an HttpOnly cookie. JavaScript
   cannot read an HttpOnly cookie, so a script injected into the page (XSS)
   cannot steal it. The browser attaches it to every request automatically.
3. Because the browser attaches cookies automatically, another website could
   trick the browser into sending a request to us (CSRF). Two defences:
     - SameSite=Lax on the cookie: the browser does not send it on
       cross-site POST/PUT/DELETE requests.
     - A CSRF token: returned in the JSON as csrfToken, kept by our frontend
       in memory, and required in the X-CSRF-Token header on every
       state-changing request. Another site cannot read our responses, so it
       cannot know the token.
4. The database stores only a hash of the session token (see security.py).
"""

import hmac
import os
import sqlite3
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .db import get_db
from .schemas import LoginIn, RegisterIn
from .security import DUMMY_HASH, hash_password, hash_token, new_token, verify_password

router = APIRouter(prefix="/api")

SESSION_COOKIE = "session"
SESSION_LIFETIME = timedelta(days=7)
# The app runs on plain http://localhost for the assessment, and browsers drop
# Secure cookies on http. Set COOKIE_SECURE=1 when serving over HTTPS.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _start_session(db: sqlite3.Connection, response: Response, user_id: int) -> str:
    """Create a session row, set the cookie, and return the CSRF token."""
    token = new_token()
    csrf_token = new_token()
    expires = datetime.now(UTC) + SESSION_LIFETIME
    db.execute(
        "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at) VALUES (?, ?, ?, ?)",
        (hash_token(token), user_id, csrf_token, expires.isoformat(timespec="seconds")),
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return csrf_token


def _session_from_request(request: Request, db: sqlite3.Connection) -> sqlite3.Row | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return db.execute(
        """SELECT s.token_hash, s.csrf_token, u.id AS user_id, u.email
           FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = ? AND s.expires_at > ?""",
        (hash_token(token), _now()),
    ).fetchone()


def require_user(request: Request, db: sqlite3.Connection = Depends(get_db)) -> sqlite3.Row:
    """Dependency for every protected route.

    - No valid session            -> 401 Unauthorized ("who are you?")
    - Valid session, but a state-changing request without the right
      X-CSRF-Token header         -> 403 Forbidden ("I know you, but no")
    """
    session = _session_from_request(request, db)
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    if request.method in UNSAFE_METHODS:
        sent = request.headers.get("X-CSRF-Token", "")
        # compare_digest: constant-time comparison (see security.py).
        if not hmac.compare_digest(sent.encode(), session["csrf_token"].encode()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")
    return session


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, response: Response, db: sqlite3.Connection = Depends(get_db)):
    try:
        cursor = db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (body.email, hash_password(body.password)),
        )
    except sqlite3.IntegrityError:
        # The UNIQUE constraint on users.email fired. Relying on the database
        # (instead of "SELECT first, then INSERT") also stays correct when two
        # registrations for the same email arrive at the same moment.
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    csrf_token = _start_session(db, response, cursor.lastrowid)
    return {"email": body.email, "csrfToken": csrf_token}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    user = db.execute(
        "SELECT id, email, password_hash FROM users WHERE email = ?", (body.email,)
    ).fetchone()
    # Always run the slow hash, even for an unknown email, so an attacker cannot
    # tell from the response time which emails have accounts.
    stored_hash = user["password_hash"] if user else DUMMY_HASH
    password_ok = verify_password(body.password, stored_hash)
    if user is None or not password_ok:
        # Same message for both cases: do not reveal whether the email exists.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    # Throw away any session the browser already had and housekeep expired ones.
    # A brand-new token on every login prevents "session fixation".
    old = request.cookies.get(SESSION_COOKIE)
    if old:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(old),))
    db.execute("DELETE FROM sessions WHERE expires_at <= ?", (_now(),))

    csrf_token = _start_session(db, response, user["id"])
    return {"email": user["email"], "csrfToken": csrf_token}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, session=Depends(require_user), db: sqlite3.Connection = Depends(get_db)):
    # Delete the session server-side: the old cookie is now useless even if
    # someone copied it. Then tell the browser to drop the cookie too.
    db.execute("DELETE FROM sessions WHERE token_hash = ?", (session["token_hash"],))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=COOKIE_SECURE)


@router.get("/me")
def me(session=Depends(require_user)):
    # csrfToken is extra to the contract's {email}: after a page reload the
    # frontend has lost the token from memory and gets it back from here.
    return {"email": session["email"], "csrfToken": session["csrf_token"]}
