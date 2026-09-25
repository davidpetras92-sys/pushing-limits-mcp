"""MCP server (stdio) for Pushing Limits Club training data."""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import transform as T
from .api import LoginFailed, PLClient

mcp = FastMCP("pushinglimits")

_client: PLClient | None = None


def client() -> PLClient:
    global _client
    if _client is None:
        _client = PLClient()
    return _client


def _login_error(exc: LoginFailed) -> dict[str, Any]:
    return {"error": "login_failed", "reason": exc.reason, "detail": exc.detail}


def _guard(fn):
    """Convert LoginFailed / generic errors to a structured error result."""

    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except LoginFailed as exc:
            return _login_error(exc)
        except ValueError as exc:
            return {"error": "bad_request", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 - surface API changes to the caller
            return {"error": "api_error", "detail": f"{type(exc).__name__}: {exc}"}

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


@mcp.tool()
@_guard
def pl_status() -> dict:
    """Login check against Pushing Limits Club. Returns logged_in, user_name, checked_at."""
    me = client().get("/user/me")
    name = None
    if isinstance(me, dict):
        name = me.get("name") or " ".join(
            p for p in (me.get("firstName") or me.get("firstname"), me.get("lastName") or me.get("lastname")) if p
        ) or me.get("email")
    return {"logged_in": True, "user_name": name, "checked_at": T.now_iso()}


@mcp.tool()
@_guard
def pl_get_pmc(start_date: str, end_date: str) -> list[dict]:
    """Performance management chart (CTL/ATL/TSB/TSS per day). Dates YYYY-MM-DD, Europe/Berlin."""
    start, end = T.parse_date(start_date), T.parse_date(end_date)
    frm, until = T.range_s(start, end)
    data = client().get("/workout/analysis/pmc", params={"from": frm, "until": until})
    rows = T.map_pmc(data)
    s, e = start.isoformat(), end.isoformat()
    return [r for r in rows if r["date"] is None or s <= r["date"] <= e]


def _fetch_workouts(start, end) -> list[dict]:
    frm, until = T.range_ms(start, end)
    data = client().get(f"/workout/from/{frm}/until/{until}")
    rows = T.map_workouts(data)
    s, e = start.isoformat(), end.isoformat()
    return [r for r in rows if r["date"] is None or s <= r["date"] <= e]


@mcp.tool()
@_guard
def pl_get_workouts(start_date: str, end_date: str) -> list[dict]:
    """Planned and completed workouts between two dates (YYYY-MM-DD, inclusive, Europe/Berlin)."""
    return _fetch_workouts(T.parse_date(start_date), T.parse_date(end_date))


@mcp.tool()
@_guard
def pl_get_week(date: str) -> dict:
    """Monday-Sunday week containing the date: TSS sums plus workouts with status erledigt/offen/ausgelassen."""
    d = T.parse_date(date)
    monday, sunday = T.week_bounds(d)
    rows = _fetch_workouts(monday, sunday)
    week = T.build_week(rows, T.today_local())
    return {"week_start": monday.isoformat(), "week_end": sunday.isoformat(), **week}


@mcp.tool()
@_guard
def pl_get_thresholds() -> dict:
    """Current thresholds: ftp, threshold_run, threshold_swim, weight, max_hr, resting_hr, updated_at."""
    return T.map_thresholds(client().get("/user/threshold"))


def main() -> None:
    # httpx logs every request at INFO; keep the Claude Desktop log quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        sys.exit(0)
