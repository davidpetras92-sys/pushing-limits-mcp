"""Read credentials from the macOS keychain.

The password never enters this repo, config files or environment variables.
It is stored once by the user via:

    security add-generic-password -s pushinglimits-mcp -a <email> -w
"""

from __future__ import annotations

import re
import subprocess

SERVICE = "pushinglimits-mcp"


class KeychainError(RuntimeError):
    pass


def _run(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["security", *args], capture_output=True, text=True, timeout=10
        )
    except FileNotFoundError as exc:  # not macOS
        raise KeychainError("security CLI not available") from exc
    except subprocess.TimeoutExpired as exc:
        raise KeychainError("keychain access timed out") from exc
    if proc.returncode != 0:
        raise KeychainError(
            f"keychain item '{SERVICE}' not found (exit {proc.returncode})"
        )
    return proc.stdout + proc.stderr


def get_account() -> str:
    """Return the account (email) stored for the service."""
    out = _run(["find-generic-password", "-s", SERVICE])
    m = re.search(r'"acct"<blob>="([^"]*)"', out)
    if not m or not m.group(1):
        raise KeychainError(f"no account attribute on keychain item '{SERVICE}'")
    return m.group(1)


def get_password(account: str) -> str:
    out = _run(["find-generic-password", "-s", SERVICE, "-a", account, "-w"])
    pw = out.strip()
    if not pw:
        raise KeychainError("empty password in keychain")
    return pw


def get_credentials() -> tuple[str, str]:
    account = get_account()
    return account, get_password(account)
