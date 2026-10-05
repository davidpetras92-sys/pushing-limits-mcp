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
    assert set(tools["pl_get_week"].inputSchema["properties"]) == {"date", "include_energy"}
    assert set(tools["pl_get_workouts"].inputSchema["properties"]) == {"start_date", "end_date", "include_energy"}
    assert "include_energy" not in tools["pl_get_workouts"].inputSchema.get("required", [])


def _energy_client(tmp_path, summary_handler):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/login_session"):
            return httpx.Response(200, json={}, headers={"set-cookie": "plc=ok; Path=/"})
        if "/workout/from/" in request.url.path:
            return httpx.Response(200, json=[
                {"_id": "w1", "localDate": "2026-10-04", "orderOfDay": 1, "name": "LIT - 2h00",
                 "sport": "Radfahren", "durationIs": 13508.042, "pss": 192, "calories": 2063},
                {"_id": "w2", "localDate": "2026-10-06", "orderOfDay": 3, "name": "Plan",
                 "sport": "Schwimmen", "durationShould": 3600, "loadEstimate": 84, "calories": 0},
            ])
        if "/workout/analysis/summary/small/" in request.url.path:
            return summary_handler(request)
        return httpx.Response(404)

    return PLClient(session_path=tmp_path / "s.json", credentials=lambda: ("a@b.c", "12345678"),
                    transport=httpx.MockTransport(handler)), calls


def test_workouts_without_energy_make_no_extra_request(tmp_path, monkeypatch):
    c, calls = _energy_client(tmp_path, lambda r: httpx.Response(500))
    monkeypatch.setattr(srv, "_client", c)
    rows = srv.pl_get_workouts("2026-10-04", "2026-10-06")
    assert not any("/analysis/summary" in p for p in calls)
    assert rows[0]["kcal_is"] == 2063 and rows[0]["carbs_g_is"] is None and rows[0]["fat_g_is"] is None
    assert rows[1]["kcal_is"] is None and rows[1]["kcal_plan"] is None


def test_workouts_with_energy(tmp_path, monkeypatch):
    def summary(request):
        assert request.url.path == "/api/workout/analysis/summary/small/from/1791064800/till/1791323999"
        return httpx.Response(200, json=[
            {"workout": {"_id": "w1"}, "total_calories": 2063, "fatPercentage": 73, "choPercentage": 27},
        ])

    c, _ = _energy_client(tmp_path, summary)
    monkeypatch.setattr(srv, "_client", c)
    rows = srv.pl_get_workouts("2026-10-04", "2026-10-06", include_energy=True)
    assert (rows[0]["kcal_is"], rows[0]["carbs_g_is"], rows[0]["fat_g_is"]) == (2063, 139, 167)
    assert rows[1]["carbs_g_is"] is None and rows[1]["carbs_g_plan"] is None


def test_failed_energy_request_keeps_workouts(tmp_path, monkeypatch):
    c, _ = _energy_client(tmp_path, lambda r: httpx.Response(502))
    monkeypatch.setattr(srv, "_client", c)
    rows = srv.pl_get_workouts("2026-10-04", "2026-10-06", include_energy=True)
    assert len(rows) == 2
    assert rows[0]["tss_is"] == 192.0 and rows[0]["kcal_is"] == 2063
    assert rows[0]["carbs_g_is"] is None and rows[0]["fat_g_is"] is None


def test_energy_limited_to_14_days(tmp_path, monkeypatch):
    c, calls = _energy_client(tmp_path, lambda r: httpx.Response(200, json=[]))
    monkeypatch.setattr(srv, "_client", c)
    out = srv.pl_get_workouts("2026-10-01", "2026-10-15", include_energy=True)
    assert out["error"] == "bad_request"
    assert calls == []
    assert isinstance(srv.pl_get_workouts("2026-10-01", "2026-10-14", include_energy=True), list)
    assert isinstance(srv.pl_get_workouts("2025-10-01", "2026-10-15"), list)
