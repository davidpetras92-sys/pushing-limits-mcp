from datetime import date

import pytest

from pushinglimits_mcp import transform as T


def test_range_ms_matches_spec_example():
    # Week 21.09. - 27.09.2026: from 2026-09-20T22:00:00Z, until 2026-09-27T21:59:59Z
    frm, until = T.range_ms(date(2026, 9, 21), date(2026, 9, 27))
    assert frm == 1789941600000
    assert until == 1790546399000


def test_range_s_is_seconds():
    frm, until = T.range_s(date(2026, 9, 21), date(2026, 9, 27))
    assert frm == 1789941600
    assert until == 1790546399


def test_range_respects_winter_time():
    # 2026-01-15 00:00 Europe/Berlin == 2025-01-14T23:00:00Z (CET, UTC+1)
    frm, _ = T.range_s(date(2026, 1, 15), date(2026, 1, 15))
    assert frm == 1768431600


def test_week_bounds_monday_to_sunday():
    assert T.week_bounds(date(2026, 9, 25)) == (date(2026, 9, 21), date(2026, 9, 27))
    assert T.week_bounds(date(2026, 9, 21)) == (date(2026, 9, 21), date(2026, 9, 27))
    assert T.week_bounds(date(2026, 9, 27)) == (date(2026, 9, 21), date(2026, 9, 27))


def test_parse_date_rejects_garbage():
    with pytest.raises(ValueError):
        T.parse_date("25.09.2026")


def test_local_date_from_ms_and_iso():
    # 2026-09-24T22:30:00Z is already 25.09. in Berlin
    assert T._local_date(1790289000000) == "2026-09-25"
    assert T._local_date("2026-09-24T22:30:00.000Z") == "2026-09-25"
    assert T._local_date("2026-09-24") == "2026-09-24"


def test_map_pmc_rounds_one_decimal():
    rows = T.map_pmc({"series": [{"day": "2026-09-25", "ctl": 98.44, "atl": 116.06, "tsb": -17.66, "load": 98}]})
    assert rows == [{"date": "2026-09-25", "ctl": 98.4, "atl": 116.1, "tsb": -17.7, "tss": 98.0}]


def test_map_workout_compact_without_description():
    w = {
        "name": "Rad GA1", "sport": "Radfahren", "localDate": "2026-09-24", "orderOfDay": 1,
        "durationIs": 3600, "durationShould": 3900, "distance": 30000, "distanceShould": 32000,
        "pss": 98.2, "loadEstimate": 100, "heartRateAvg": 135.6, "heartRateAvgShould": 140,
        "powerInWatts": 210, "belongsToActivatedPlan": True, "description": "long text",
    }
    row = T.map_workout(w)
    assert "description" not in row
    assert row["duration_min_is"] == 60.0
    assert row["duration_min_plan"] == 65.0
    assert row["tss_is"] == 98.2 and row["tss_plan"] == 100.0
    assert row["hr_avg_is"] == 136
    assert row["planned"] is True


def test_map_workouts_sorted_by_date_and_order():
    rows = T.map_workouts([
        {"localDate": "2026-09-22", "orderOfDay": 2},
        {"localDate": "2026-09-21", "orderOfDay": 1},
        {"localDate": "2026-09-22", "orderOfDay": 1},
    ])
    assert [(r["date"], r["order"]) for r in rows] == [
        ("2026-09-21", 1), ("2026-09-22", 1), ("2026-09-22", 2)
    ]


def test_workout_status_rules():
    today = date(2026, 9, 25)
    done = {"date": "2026-09-20", "duration_min_is": 45.0}
    past_open = {"date": "2026-09-24", "duration_min_is": None}
    today_open = {"date": "2026-09-25", "duration_min_is": 0.0}
    future = {"date": "2026-09-27", "duration_min_is": None}
    assert T.workout_status(done, today) == "erledigt"
    assert T.workout_status(past_open, today) == "ausgelassen"
    assert T.workout_status(today_open, today) == "offen"
    assert T.workout_status(future, today) == "offen"


def test_build_week_sums():
    rows = [
        {"date": "2026-09-21", "duration_min_is": 60.0, "tss_is": 80.0, "tss_plan": 85.0},
        {"date": "2026-09-23", "duration_min_is": None, "tss_is": None, "tss_plan": 120.0},
    ]
    week = T.build_week(rows, date(2026, 9, 22))
    assert week["tss_is_sum"] == 80.0
    assert week["tss_plan_sum"] == 205.0
    assert [w["status"] for w in week["workouts"]] == ["erledigt", "offen"]


def test_map_thresholds():
    t = {"ftp": 280, "threshold_run": 240, "threshold_swim": 95, "weight": 75.5,
         "maxHr": 185, "restingHr": 48, "createdAt": "2026-09-01T10:00:00Z"}
    assert T.map_thresholds(t) == {
        "ftp": 280, "threshold_run": 240, "threshold_swim": 95, "weight": 75.5,
        "max_hr": 185, "resting_hr": 48, "updated_at": "2026-09-01T10:00:00Z",
    }
