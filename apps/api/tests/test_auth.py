"""Sign-up and two-step login against a fake Supabase Auth (GoTrue).

The fake speaks GoTrue's REST shapes at the network boundary; everything
on this side — the challenge window, rate limits, the recorded-session
gate in app/deps.py — runs for real. The bypass tests are the point: a
session obtained from Supabase without going through both steps here
must not open the API.
"""
import base64
import json
import uuid

import httpx
import pytest
import respx

SUPABASE = "https://proj.supabase.co"


def _jwt(sub: str, session_id: str) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{enc({'alg': 'none'})}.{enc({'sub': sub, 'session_id': session_id})}.sig"


class FakeGoTrue:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}  # access_token -> {user, session_id, revoked}
        self.refresh: dict[str, str] = {}  # refresh_token -> session_id
        self.codes: dict[str, str] = {}
        self.codes_sent = 0
        self.signed_out: list[str] = []
        self.deleted: list[str] = []

    def _session(self, user: dict, session_id: str | None = None) -> dict:
        session_id = session_id or str(uuid.uuid4())
        access = _jwt(user["id"], session_id) + uuid.uuid4().hex[:6]
        refresh = uuid.uuid4().hex
        self.sessions[access] = {"user": user, "session_id": session_id, "revoked": False}
        self.refresh[refresh] = session_id
        return {"access_token": access, "refresh_token": refresh, "expires_in": 3600, "expires_at": 2_000_000_000, "user": user}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/auth/v1")
        body = json.loads(request.content or b"{}")
        grant = request.url.params.get("grant_type")
        if path == "/admin/users" and request.method == "POST":
            if body["email"] in self.users:
                return httpx.Response(422, json={"msg": "A user with this email address has already been registered"})
            self.users[body["email"]] = {"id": str(uuid.uuid4()), "email": body["email"], "password": body["password"]}
            return httpx.Response(200, json=self.users[body["email"]])
        if path.startswith("/admin/users/") and request.method == "DELETE":
            self.deleted.append(path.rsplit("/", 1)[1])
            return httpx.Response(200, json={})
        if path == "/token" and grant == "password":
            user = self.users.get(body["email"])
            if not user or user["password"] != body["password"]:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Invalid login credentials"})
            return httpx.Response(200, json=self._session(user))
        if path == "/token" and grant == "refresh_token":
            sid = self.refresh.pop(body["refresh_token"], None)
            live = [s for s in self.sessions.values() if s["session_id"] == sid and not s["revoked"]]
            if not live:
                return httpx.Response(400, json={"error_description": "Invalid Refresh Token"})
            return httpx.Response(200, json=self._session(live[0]["user"], sid))
        if path == "/logout":
            token = request.headers["Authorization"].removeprefix("Bearer ")
            sid = self.sessions[token]["session_id"]
            for s in self.sessions.values():
                if s["session_id"] == sid:
                    s["revoked"] = True
            self.signed_out.append(sid)
            return httpx.Response(204)
        if path == "/otp":
            assert body.get("create_user") is False
            if body["email"] in self.users:
                self.codes[body["email"]] = "246810"
                self.codes_sent += 1
            return httpx.Response(200, json={})
        if path == "/admin/generate_link" and request.method == "POST":
            assert body["type"] == "magiclink" and request.headers["apikey"] == "service"
            if body["email"] not in self.users:
                return httpx.Response(404, json={"msg": "User not found"})
            self.codes[body["email"]] = "135790"
            return httpx.Response(200, json={**self.users[body["email"]], "email_otp": "135790", "verification_type": "magiclink"})
        if path == "/verify":
            if self.codes.get(body["email"]) != body["token"]:
                return httpx.Response(403, json={"msg": "Token has expired or is invalid"})
            del self.codes[body["email"]]
            return httpx.Response(200, json=self._session(self.users[body["email"]]))
        if path == "/user":
            token = request.headers["Authorization"].removeprefix("Bearer ")
            s = self.sessions.get(token)
            if not s or s["revoked"]:
                return httpx.Response(401, json={"msg": "invalid JWT"})
            return httpx.Response(200, json=s["user"])
        return httpx.Response(404, json={"msg": f"unhandled {request.method} {path}"})


@pytest.fixture
def gotrue(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    from app.config import get_settings

    get_settings.cache_clear()
    fake = FakeGoTrue()
    with respx.mock(assert_all_called=False) as router:
        router.route(host="proj.supabase.co").mock(side_effect=fake.handler)
        router.route(host="test").pass_through()
        fake.router = router  # for tests that also fake the email provider
        yield fake


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


SIGNUP = {"email": "maria@example.com", "password": "correct horse 42", "accept_terms": True, "confirm_age": True}


async def _signup(client, **over):
    return await client.post("/auth/signup", json={**SIGNUP, **over})


async def test_signup_requires_terms_and_age(client, gotrue):
    assert (await _signup(client, accept_terms=False)).status_code == 422
    assert (await _signup(client, confirm_age=False)).status_code == 422
    assert gotrue.users == {}


async def test_signup_signs_you_straight_in_and_records_consent(client, gotrue):
    r = await _signup(client)
    assert r.status_code == 201, r.text
    session = r.json()
    me = await client.get("/auth/me", headers=bearer(session["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "maria@example.com"
    assert me.json()["terms_version"]

    again = await _signup(client)
    assert again.status_code == 409


async def test_login_needs_password_then_emailed_code(client, gotrue):
    await _signup(client)

    wrong = await client.post("/auth/login", json={"email": SIGNUP["email"], "password": "nope"})
    assert wrong.status_code == 401
    assert gotrue.codes_sent == 0

    start = await client.post("/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]})
    assert start.status_code == 200, start.text
    assert gotrue.codes_sent == 1
    # The session the password check produced was signed out at Supabase.
    assert len(gotrue.signed_out) == 1

    bad = await client.post("/auth/login/verify", json={"email": SIGNUP["email"], "code": "000000"})
    assert bad.status_code == 400

    ok = await client.post("/auth/login/verify", json={"email": SIGNUP["email"], "code": "246810"})
    assert ok.status_code == 200, ok.text
    assert (await client.get("/auth/me", headers=bearer(ok.json()["access_token"]))).status_code == 200


async def test_a_password_only_session_from_supabase_is_refused(client, gotrue):
    """Someone with the password who skips this API and asks Supabase for a
    session directly gets a real Supabase token — and this API refuses it."""
    await _signup(client)
    user = gotrue.users[SIGNUP["email"]]
    direct = gotrue._session(user)
    assert (await client.get("/auth/me", headers=bearer(direct["access_token"]))).status_code == 401


async def test_an_emailed_code_alone_does_not_open_the_api(client, gotrue):
    """Someone who only has the inbox (no password) can get Supabase to send
    a code and verify it directly — that session is refused here too."""
    await _signup(client)
    gotrue.codes[SIGNUP["email"]] = "111111"
    r = await client.post("/auth/login/verify", json={"email": SIGNUP["email"], "code": "111111"})
    assert r.status_code == 400  # no password-checked window open
    direct = gotrue._session(gotrue.users[SIGNUP["email"]])
    assert (await client.get("/auth/me", headers=bearer(direct["access_token"]))).status_code == 401


async def test_repeated_wrong_passwords_are_rate_limited(client, gotrue):
    await _signup(client)
    for _ in range(5):
        r = await client.post("/auth/login", json={"email": SIGNUP["email"], "password": "wrong"})
        assert r.status_code == 401
    r = await client.post("/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]})
    assert r.status_code == 429


async def test_resend_is_limited_per_password_check(client, gotrue):
    await _signup(client)
    await client.post("/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]})
    assert (await client.post("/auth/login/resend", json={"email": SIGNUP["email"]})).status_code == 200
    assert (await client.post("/auth/login/resend", json={"email": SIGNUP["email"]})).status_code == 200
    assert (await client.post("/auth/login/resend", json={"email": SIGNUP["email"]})).status_code == 429
    assert gotrue.codes_sent == 3


async def test_too_many_wrong_codes_closes_the_window(client, gotrue):
    await _signup(client)
    await client.post("/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]})
    for _ in range(5):
        await client.post("/auth/login/verify", json={"email": SIGNUP["email"], "code": "000000"})
    r = await client.post("/auth/login/verify", json={"email": SIGNUP["email"], "code": "246810"})
    assert r.status_code == 400


async def test_refresh_and_logout(client, gotrue):
    session = (await _signup(client)).json()
    refreshed = await client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    token = refreshed.json()["access_token"]
    assert (await client.get("/auth/me", headers=bearer(token))).status_code == 200

    assert (await client.post("/auth/logout", headers=bearer(token))).status_code == 204
    assert (await client.get("/auth/me", headers=bearer(token))).status_code == 401
    again = await client.post("/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]})
    assert again.status_code == 401


async def test_deleting_the_account_removes_the_supabase_user(client, gotrue):
    session = (await _signup(client)).json()
    r = await client.request("DELETE", "/me", json={"confirm": "DELETE"}, headers=bearer(session["access_token"]))
    assert r.status_code == 200, r.text
    assert gotrue.deleted == [session["user"]["id"]]
    assert (await client.get("/auth/me", headers=bearer(session["access_token"]))).status_code == 401


async def test_with_an_email_provider_warden_sends_the_code_itself(client, gotrue, monkeypatch):
    """Supabase only generates the code (no template, no SMTP involved);
    the email goes out through Resend and the code works the same way."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM", "Warden <onboarding@resend.dev>")
    from app.config import get_settings

    get_settings.cache_clear()
    sent = []
    gotrue.router.post("https://api.resend.com/emails").mock(
        side_effect=lambda request: sent.append(json.loads(request.content)) or httpx.Response(200, json={"id": "em_1"})
    )
    await _signup(client)
    r = await client.post("/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]})
    assert r.status_code == 200, r.text
    assert gotrue.codes_sent == 0  # Supabase sent nothing
    [email] = sent
    assert email["to"] == [SIGNUP["email"]] and email["from"] == "Warden <onboarding@resend.dev>"
    assert "135790" in email["text"] and email["subject"] == "Your Warden sign-in code"

    ok = await client.post("/auth/login/verify", json={"email": SIGNUP["email"], "code": "135790"})
    assert ok.status_code == 200, ok.text


async def test_a_refused_code_email_is_explained(client, gotrue, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    from app.config import get_settings

    get_settings.cache_clear()
    gotrue.router.post("https://api.resend.com/emails").mock(
        return_value=httpx.Response(403, json={"message": "You can only send testing emails to your own email address"})
    )
    await _signup(client)
    r = await client.post("/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]})
    assert r.status_code == 502 and "test mode" in r.json()["detail"]
