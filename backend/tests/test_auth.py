from conftest import make_client, register


def test_register_starts_a_session():
    client = make_client()
    csrf = register(client)
    assert csrf
    assert "session" in client.cookies
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["email"] == "ann@example.com"


def test_session_cookie_is_httponly_and_samesite():
    client = make_client()
    r = client.post("/api/register", json={"email": "a@b.nl", "password": "12345678"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_duplicate_email_is_409_case_insensitive():
    client = make_client()
    register(client, email="ann@example.com")
    r = make_client().post("/api/register", json={"email": " ANN@example.com ", "password": "something long"})
    assert r.status_code == 409


def test_register_validation_gives_message_per_field():
    r = make_client().post("/api/register", json={"email": "not-an-email", "password": "short"})
    assert r.status_code == 422
    assert set(r.json()["errors"]) == {"email", "password"}


def test_login_wrong_password_and_unknown_email_look_the_same():
    register(make_client())
    wrong = make_client().post("/api/login", json={"email": "ann@example.com", "password": "nope nope"})
    unknown = make_client().post("/api/login", json={"email": "who@example.com", "password": "nope nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_works_and_gives_new_session():
    register(make_client())
    client = make_client()
    r = client.post("/api/login", json={"email": "ann@example.com", "password": "correct horse"})
    assert r.status_code == 200
    assert r.json()["csrfToken"]
    assert client.get("/api/me").status_code == 200


def test_me_without_session_is_401():
    assert make_client().get("/api/me").status_code == 401


def test_forged_cookie_is_401():
    client = make_client()
    client.cookies.set("session", "made-up-token")
    assert client.get("/api/me").status_code == 401


def test_logout_needs_csrf_token():
    client = make_client()
    register(client)
    assert client.post("/api/logout").status_code == 403
    assert client.post("/api/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403


def test_logout_ends_session_server_side():
    client = make_client()
    csrf = register(client)
    stolen_cookie = client.cookies.get("session")
    assert client.post("/api/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/me").status_code == 401
    # Even a copy of the old cookie no longer works.
    other = make_client()
    other.cookies.set("session", stolen_cookie)
    assert other.get("/api/me").status_code == 401


def test_password_is_not_stored_in_plain_text():
    from app import db

    register(make_client(), password="correct horse")
    with db.connect() as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert "correct horse" not in stored
    assert stored.startswith("scrypt$")
