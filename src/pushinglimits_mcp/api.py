"""HTTP client for the Pushing Limits Club JSON API.

Session logic: load cookies -> request -> on 401/403 log in exactly once
(credentials from keychain) -> retry once -> otherwise raise LoginFailed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import httpx

from . import keychain, session

BASE_URL = "https://pushinglimits.club/api"
TIMEOUT = 20.0
COOKIE_DOMAIN = "pushinglimits.club"

CredentialsProvider = Callable[[], tuple[str, str]]


class LoginFailed(RuntimeError):
    """Raised when no valid session can be established."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class PLClient:
    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        session_path: Path = session.DEFAULT_SESSION_PATH,
        credentials: CredentialsProvider = keychain.get_credentials,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.session_path = session_path
        self._credentials = credentials
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=TIMEOUT,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "pushinglimits-mcp/0.1"},
        )
        self._restore_cookies()

    # -- session persistence -------------------------------------------------

    def _restore_cookies(self) -> None:
        for c in session.load(self.session_path):
            self._http.cookies.set(
                c["name"], c["value"], domain=c.get("domain") or COOKIE_DOMAIN, path=c.get("path") or "/"
            )

    def _persist_cookies(self) -> None:
        cookies = [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
            for c in self._http.cookies.jar
        ]
        session.save(cookies, self.session_path)

    @property
    def has_session(self) -> bool:
        return any(session.is_session_cookie(c.name) for c in self._http.cookies.jar)

    # -- login ---------------------------------------------------------------

    def login(self) -> None:
        try:
            email, password = self._credentials()
        except keychain.KeychainError as exc:
            raise LoginFailed("keychain", str(exc)) from exc

        # Drop any stale session cookies before logging in again.
        self._http.cookies.clear()
        try:
            resp = self._http.post("/user/login_session", json={"email": email, "password": password})
        except httpx.HTTPError as exc:
            raise LoginFailed("network", str(exc)) from exc

        if resp.status_code == 428:
            raise LoginFailed(
                "captcha_required",
                "Pushing Limits verlangt ein Captcha. Einmal im Browser einloggen (scripts/login_browser.py) "
                "oder später erneut versuchen.",
            )
        if resp.status_code in (400, 401, 403):
            raise LoginFailed("bad_credentials", f"HTTP {resp.status_code} beim Login")
        if resp.status_code != 200:
            raise LoginFailed("unexpected_status", f"HTTP {resp.status_code} beim Login")
        if not self.has_session:
            raise LoginFailed("no_cookie", "Login-Antwort enthielt kein Session-Cookie")
        self._persist_cookies()

    # -- requests ------------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.has_session:
            self.login()
            return self._get_or_fail(path, params)

        resp = self._request(path, params)
        if resp.status_code in (401, 403):
            self.login()
            return self._get_or_fail(path, params)
        return self._parse(resp)

    def _get_or_fail(self, path: str, params: dict[str, Any] | None) -> Any:
        resp = self._request(path, params)
        if resp.status_code in (401, 403):
            raise LoginFailed("session_rejected", f"HTTP {resp.status_code} direkt nach erfolgreichem Login")
        return self._parse(resp)

    def _request(self, path: str, params: dict[str, Any] | None) -> httpx.Response:
        try:
            return self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise LoginFailed("network", str(exc)) from exc

    @staticmethod
    def _parse(resp: httpx.Response) -> Any:
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} for {resp.request.url.path}")
        try:
            return resp.json()
        except ValueError as exc:
            raise RuntimeError(f"non-JSON response for {resp.request.url.path}") from exc

    def close(self) -> None:
        self._http.close()
