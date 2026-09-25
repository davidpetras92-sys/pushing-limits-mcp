import json
import os
import stat

import httpx
import pytest

from pushinglimits_mcp import session
from pushinglimits_mcp.api import LoginFailed, PLClient


class FakeAPI:
    """Minimal stand-in for pushinglimits.club: cookie 'plc' == 'good' is a valid session."""

    def __init__(self):
        self.calls = []
        self.login_status = 200
        self.valid = {"good"}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        cookie = request.headers.get("cookie", "")
        if request.url.path == "/api/user/login_session":
            body = json.loads(request.content)
            assert body == {"email": "me@example.com", "password": "secret-pw"}
            if self.login_status != 200:
                return httpx.Response(self.login_status, json={"code": "CAPTCHA_REQUIRED", "siteKey": "x"})
            return httpx.Response(
                200,
                json={"user": {"name": "Tester"}},
                headers=[
                    ("set-cookie", "plc=good; Path=/; HttpOnly; Secure"),
                    ("set-cookie", "__cf_bm=cf; Path=/; HttpOnly"),
                ],
            )
        if any(f"plc={v}" in cookie for v in self.valid):
            return httpx.Response(200, json={"name": "Tester", "path": request.url.path})
        return httpx.Response(401, json={"error": "unauthorized"})


@pytest.fixture
def api():
    return FakeAPI()


@pytest.fixture
def session_path(tmp_path):
    return tmp_path / "session.json"


def make_client(api, session_path):
    return PLClient(
        base_url="https://pushinglimits.club/api",
        session_path=session_path,
        credentials=lambda: ("me@example.com", "secret-pw"),
        transport=httpx.MockTransport(api.handler),
    )


def test_no_session_logs_in_first_then_requests(api, session_path):
    c = make_client(api, session_path)
    assert c.get("/user/me")["name"] == "Tester"
    assert [p for _, p in api.calls] == ["/api/user/login_session", "/api/user/me"]
    # Session persisted with 600 and without Cloudflare cookies
    assert session_path.exists()
    assert stat.S_IMODE(os.stat(session_path).st_mode) == 0o600
    names = [c["name"] for c in json.loads(session_path.read_text())["cookies"]]
    assert names == ["plc"]


def test_valid_stored_session_is_reused_without_login(api, session_path):
    session.save([{"name": "plc", "value": "good", "domain": "pushinglimits.club", "path": "/"}], session_path)
    c = make_client(api, session_path)
    c.get("/user/threshold")
    assert [p for _, p in api.calls] == ["/api/user/threshold"]


def test_expired_session_relogs_exactly_once_and_retries(api, session_path):
    session.save([{"name": "plc", "value": "stale", "domain": "pushinglimits.club", "path": "/"}], session_path)
    c = make_client(api, session_path)
    assert c.get("/user/me")["name"] == "Tester"
    assert [p for _, p in api.calls] == ["/api/user/me", "/api/user/login_session", "/api/user/me"]
    # stored session replaced by the fresh one
    stored = json.loads(session_path.read_text())["cookies"]
    assert stored[0]["value"] == "good"


def test_still_unauthorized_after_login_fails_without_loop(api, session_path):
    api.valid = set()  # server never accepts any cookie
    c = make_client(api, session_path)
    with pytest.raises(LoginFailed) as ei:
        c.get("/user/me")
    assert ei.value.reason == "session_rejected"
    assert [p for _, p in api.calls] == ["/api/user/login_session", "/api/user/me"]


def test_captcha_required_reported_as_login_failed(api, session_path):
    api.login_status = 428
    c = make_client(api, session_path)
    with pytest.raises(LoginFailed) as ei:
        c.get("/user/me")
    assert ei.value.reason == "captcha_required"
    assert not session_path.exists()


def test_bad_credentials(api, session_path):
    api.login_status = 401
    c = make_client(api, session_path)
    with pytest.raises(LoginFailed) as ei:
        c.get("/user/me")
    assert ei.value.reason == "bad_credentials"


def test_session_load_ignores_cloudflare_cookies(session_path):
    session_path.write_text(json.dumps({"cookies": [
        {"name": "__cf_bm", "value": "x"}, {"name": "plc", "value": "good"}
    ]}))
    assert [c["name"] for c in session.load(session_path)] == ["plc"]


def test_session_load_missing_or_corrupt(session_path):
    assert session.load(session_path) == []
    session_path.write_text("{not json")
    assert session.load(session_path) == []
