"""Time-zone handling, week logic and field mapping (pure functions, no I/O)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")


# -- dates / time boundaries -------------------------------------------------

def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Datum muss YYYY-MM-DD sein, nicht {value!r}") from exc


def day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=TZ)


def day_end(d: date) -> datetime:
    """23:59:59 local time of the given day."""
    return datetime.combine(d, time(23, 59, 59), tzinfo=TZ)


def range_ms(start: date, end: date) -> tuple[int, int]:
    return int(day_start(start).timestamp() * 1000), int(day_end(end).timestamp() * 1000)


def range_s(start: date, end: date) -> tuple[int, int]:
    return int(day_start(start).timestamp()), int(day_end(end).timestamp())


def week_bounds(d: date) -> tuple[date, date]:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def today_local(now: datetime | None = None) -> date:
    now = now or datetime.now(tz=TZ)
    return now.astimezone(TZ).date()


def now_iso() -> str:
    return datetime.now(tz=TZ).replace(microsecond=0).isoformat()


# -- helpers -----------------------------------------------------------------

def r1(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _minutes(seconds: Any) -> float | None:
    if seconds in (None, 0, "0"):
        return None if seconds is None else 0.0
    try:
        return round(float(seconds) / 60.0, 1)
    except (TypeError, ValueError):
        return None


def _local_date(value: Any) -> str | None:
    """Normalise the API's day/date representations to YYYY-MM-DD (Europe/Berlin)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e11:  # milliseconds
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=TZ).date().isoformat()
    s = str(value)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        if len(s) > 10 and ("T" in s or " " in s):
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    return dt.astimezone(TZ).date().isoformat()
            except ValueError:
                pass
        return s[:10]
    return s


# -- mapping -----------------------------------------------------------------

def map_pmc(payload: Any) -> list[dict]:
    series = payload.get("series", []) if isinstance(payload, dict) else payload
    out = []
    for row in series or []:
        out.append(
            {
                "date": _local_date(row.get("day") or row.get("date")),
                "ctl": r1(row.get("ctl")),
                "atl": r1(row.get("atl")),
                "tsb": r1(row.get("tsb")),
                "tss": r1(row.get("load") if row.get("load") is not None else row.get("tss")),
            }
        )
    return out


def map_workout(w: dict) -> dict:
    return {
        "date": _local_date(w.get("localDate") or w.get("date")),
        "order": w.get("orderOfDay"),
        "name": w.get("name"),
        "sport": w.get("sport"),
        "planned": bool(w.get("belongsToActivatedPlan")),
        "duration_min_is": _minutes(w.get("durationIs")),
        "duration_min_plan": _minutes(w.get("durationShould")),
        "distance_is": w.get("distance"),
        "distance_plan": w.get("distanceShould"),
        "tss_is": r1(w.get("pss")),
        "tss_plan": r1(w.get("loadEstimate")),
        "hr_avg_is": _int_or_none(w.get("heartRateAvg")),
        "hr_avg_plan": _int_or_none(w.get("heartRateAvgShould")),
        "power_avg_is": _int_or_none(w.get("powerInWatts")),
    }


def map_workouts(payload: Any) -> list[dict]:
    items = payload
    if isinstance(payload, dict):
        items = payload.get("workouts") or payload.get("data") or []
    rows = [map_workout(w) for w in items or [] if isinstance(w, dict)]
    rows.sort(key=lambda r: (r["date"] or "", r["order"] if r["order"] is not None else 0))
    return rows


def workout_status(row: dict, today: date) -> str:
    """erledigt = has actual duration; ausgelassen = day is over without one; else offen."""
    if (row.get("duration_min_is") or 0) > 0:
        return "erledigt"
    d = row.get("date")
    if d and parse_date(d) < today:
        return "ausgelassen"
    return "offen"


def build_week(rows: list[dict], today: date) -> dict:
    workouts = []
    for r in rows:
        workouts.append({**r, "status": workout_status(r, today)})
    return {
        "tss_is_sum": r1(sum(r["tss_is"] or 0 for r in rows)),
        "tss_plan_sum": r1(sum(r["tss_plan"] or 0 for r in rows)),
        "workouts": workouts,
    }


def map_thresholds(t: Any) -> dict:
    t = t or {}
    if isinstance(t, list):
        t = t[0] if t else {}
    return {
        "ftp": t.get("ftp"),
        "threshold_run": t.get("threshold_run"),
        "threshold_swim": t.get("threshold_swim"),
        "weight": t.get("weight"),
        "max_hr": t.get("maxHr"),
        "resting_hr": t.get("restingHr"),
        "updated_at": t.get("updatedAt") or t.get("createdAt"),
    }
