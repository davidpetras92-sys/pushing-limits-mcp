"""Persist the login cookies outside the repo with owner-only permissions."""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_SESSION_PATH = (
    Path.home() / "Library" / "Application Support" / "pushinglimits-mcp" / "session.json"
)

# Cloudflare bot-management cookies are short-lived and not part of the login
# session. Persisting them would make the server think it has a session when
# it does not.
_IGNORED_PREFIXES = ("__cf", "cf_")


def is_session_cookie(name: str) -> bool:
    return not name.startswith(_IGNORED_PREFIXES)


def load(path: Path = DEFAULT_SESSION_PATH) -> list[dict]:
    """Return stored cookies as a list of {name, value, domain, path}."""
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    cookies = data.get("cookies", []) if isinstance(data, dict) else []
    return [c for c in cookies if isinstance(c, dict) and is_session_cookie(c.get("name", ""))]


def save(cookies: list[dict], path: Path = DEFAULT_SESSION_PATH) -> None:
    cookies = [c for c in cookies if is_session_cookie(c.get("name", ""))]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"cookies": cookies}, fh)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def clear(path: Path = DEFAULT_SESSION_PATH) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
