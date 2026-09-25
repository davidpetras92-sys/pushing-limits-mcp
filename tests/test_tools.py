"""Tool-level tests: the MCP tools return structured errors instead of raising."""

import asyncio

import httpx

import pushinglimits_mcp as srv
from pushinglimits_mcp.api import PLClient


def test_pl_status_returns_login_failed_dict(tmp_path, monkeypatch):
    def handler(request):
        if request.url.path.endswith("/login_session"):
            return httpx.Response(401, json={})
        return httpx.Response(401, json={})

    monkeypatch.setattr(
        srv, "_client",
        PLClient(session_path=tmp_path / "s.json", credentials=lambda: ("a@b.c", "12345678"),
                 transport=httpx.MockTransport(handler)),
    )
    out = srv.pl_status()
    assert out["error"] == "login_failed"
    assert out["reason"] == "bad_credentials"


def test_pl_get_week_end_to_end(tmp_path, monkeypatch):
    def handler(request):
        if request.url.path.endswith("/login_session"):
            return httpx.Response(200, json={}, headers={"set-cookie": "plc=ok; Path=/"})
        if "/workout/from/" in request.url.path:
            assert request.url.path == "/api/workout/from/1789941600000/until/1790546399000"
            return httpx.Response(200, json=[
                {"localDate": "2026-09-22", "orderOfDay": 1, "name": "Lauf", "sport": "Laufen",
                 "durationIs": 3000, "durationShould": 3000, "pss": 60, "loadEstimate": 62,
                 "belongsToActivatedPlan": True},
                {"localDate": "2026-09-26", "orderOfDay": 1, "name": "Long Ride", "sport": "Rad",
                 "durationIs": 0, "durationShould": 14400, "loadEstimate": 250,
                 "belongsToActivatedPlan": True},
            ])
        return httpx.Response(404)

    monkeypatch.setattr(
        srv, "_client",
        PLClient(session_path=tmp_path / "s.json", credentials=lambda: ("a@b.c", "12345678"),
                 transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(srv.T, "today_local", lambda: srv.T.date(2026, 9, 25))
    week = srv.pl_get_week("2026-09-25")
    assert week["week_start"] == "2026-09-21" and week["week_end"] == "2026-09-27"
    assert week["tss_is_sum"] == 60.0 and week["tss_plan_sum"] == 312.0
    assert [w["status"] for w in week["workouts"]] == ["erledigt", "offen"]


def test_tool_schemas_expose_real_parameters():
    """The error wrapper must not hide the tool signature (regression: args/kwargs schema)."""
    tools = {t.name: t for t in asyncio.run(srv.mcp.list_tools())}
    assert set(tools) == {"pl_status", "pl_get_pmc", "pl_get_workouts", "pl_get_week", "pl_get_thresholds"}
    assert tools["pl_status"].inputSchema.get("properties", {}) == {}
    assert set(tools["pl_get_pmc"].inputSchema["properties"]) == {"start_date", "end_date"}
    assert set(tools["pl_get_week"].inputSchema["properties"]) == {"date"}
