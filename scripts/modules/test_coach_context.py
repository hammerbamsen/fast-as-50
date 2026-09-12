# -*- coding: utf-8 -*-
"""Tests for coach_context.py — coach v2's kontekst som data."""
import json
import os
from datetime import date

from modules import coach_context as cc
from modules import plan_tab

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _plan():
    with open(os.path.join(_ROOT, "data", "plan.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _data():
    with open(os.path.join(_ROOT, "data.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _ws(day, label, disc, done, today=False, **kw):
    d = {"day": day, "label": label, "disc": disc, "done": done, "planned_tss": 30, "planned_mins": 45}
    if today:
        d["today"] = True
    d.update(kw)
    return d


# ── Grounding: done-pas lander aldrig i remaining ───────────────────────────

def test_done_session_never_in_remaining():
    plan = _plan()
    data = {"week_sessions": [
        _ws("Man", "Styrke", "strength", True, actual_mins=25, actual_tss=15),
        _ws("Tir", "Cykel Z2", "bike", True, actual_mins=60, actual_tss=40),
        _ws("Ons", "Løb Z2", "run", False),                 # dag passeret -> misset
        _ws("Tor", "Svøm", "swim", False, today=True),      # i dag
        _ws("Fre", "Løb let", "run", False),                # fremtid
        _ws("Lør", "Lang cykel", "bike", True),             # done i fremtiden (forudregistreret) -> completed
        _ws("Tir", "Gang", "walk", True, extra=True, actual_mins=40),
    ]}
    ctx = cc.build_context(plan, data, date(2026, 9, 10))   # torsdag
    wk = ctx["week"]
    names = lambda k: [r["name"] for r in wk[k]]
    assert names("completed") == ["Styrke", "Cykel Z2", "Lang cykel"]
    assert names("missed") == ["Løb Z2"]
    assert names("remaining") == ["Løb let"]
    assert names("extras") == ["Gang"]
    assert all(not r["done"] for r in wk["remaining"])
    assert wk["counts"] == {"completed": 3, "missed": 1, "remaining": 1}
    # dagens pas står under today, ikke i ugelisterne
    assert [s["name"] for s in ctx["today"]["sessions"]] == ["Svøm"]
    assert ctx["today"]["weekday"] == 3 and ctx["today"]["weekdayName"] == "torsdag"


# ── Cut ─────────────────────────────────────────────────────────────────────

WP = {"startKg": 72.2, "targetKg": 68, "targetDate": "2027-01-31", "cutStartsFrom": "2026-09-21",
      "maxLossPerWeekKg": 0.25}


def test_cut_inactive_before_cut_starts_from():
    c = cc.cut_status(WP, date(2026, 9, 10), 72.5)
    assert c["active"] is False
    assert c.get("expectedKg") is None and c.get("deltaVsPlan") is None
    assert c["daysToStart"] == 11
    assert c["ratePerWeek"] == 0.22


def test_cut_inactive_without_cut_starts_from():
    wp = dict(WP); wp.pop("cutStartsFrom")
    c = cc.cut_status(wp, date(2026, 10, 10), 72.0)
    assert c["active"] is False and c.get("weekOf") is None


def test_cut_expected_kg_linear():
    # 132 dage fra 21/9-2026 til 31/1-2027; 4,2 kg tab
    c = cc.cut_status(WP, date(2026, 9, 21), 72.5)
    assert c["active"] and c["weekOf"] == 1 and c["expectedKg"] == 72.2
    assert c["deltaVsPlan"] == 0.3
    mid = date(2026, 11, 26)  # 66 dage = halvvejs
    c = cc.cut_status(WP, mid, 70.0)
    assert c["expectedKg"] == 70.1
    assert c["deltaVsPlan"] == -0.1
    assert c["weekOf"] == 10
    c = cc.cut_status(WP, date(2027, 1, 31), 68.4)
    assert c["expectedKg"] == 68.0 and c["deltaVsPlan"] == 0.4
    # efter targetDate: vedligehold -> ikke aktivt
    assert cc.cut_status(WP, date(2027, 3, 1), 68.0)["active"] is False


def test_cut_from_real_plan_on_first_cut_day():
    plan = _plan()
    ctx = cc.build_context(plan, {"weightMovingAvg7": [72.4]}, date(2026, 9, 21))
    cut = ctx["body"]["cut"]
    assert ctx["program"]["id"] == "tds-2027"
    assert cut["active"] is True and cut["startsFrom"] == "2026-09-21" and cut["weekOf"] == 1
    assert cut["expectedKg"] == 72.2 and cut["deltaVsPlan"] == 0.2
    assert ctx["rules"]["cutRateKgPerWeek"] == 0.25


# ── Ingen None-crash ────────────────────────────────────────────────────────

def test_build_context_without_history_does_not_crash():
    plan = _plan()
    ctx = cc.build_context(plan, {}, date(2026, 9, 8))
    json.dumps(ctx)  # serialiserbar
    assert ctx["fitness"]["ctl"] is None and ctx["readiness"]["hrv"] is None
    assert ctx["body"]["weightAvg7"] is None and ctx["body"]["cut"]["active"] is False
    assert ctx["habits"]["afWeek"] is None and ctx["habits"]["energyAvg7"] is None
    assert ctx["week"]["remaining"] == [] and ctx["today"]["sessions"] == []
    assert ctx["readiness"]["band"] == "NORMAL"
    assert ctx["nextRace"]["name"] == "CPH Half" and ctx["nextRace"]["daysTo"] == 12


def test_build_context_history_with_none_rows():
    plan = _plan()
    data = {"hrvHistory": [None, {"date": "2026-09-05", "v": 54.0, "real": True}, None],
            "sleepHistory": [{"date": "2026-09-05", "v": 4.1}, None],
            "weightHistory": [None, None], "weightMovingAvg7": [None, 72.4, None],
            "af_history": [None, {"week": 13, "done": 6, "total": 7}],
            "checkinLog": [{"date": "2026-09-05", "alkohol": 2, "protein": None, "energi": 3, "sult": None}]}
    ctx = cc.build_context(plan, data, date(2026, 9, 6))
    assert ctx["readiness"]["hrv"] == 54.0 and ctx["readiness"]["sleepLast"] == 4.1
    assert ctx["readiness"]["band"] == "LOW"
    assert ctx["body"]["weightAvg7"] == 72.4 and ctx["body"]["weight"] is None
    assert ctx["habits"]["afAvg4"] == 6.0 and ctx["habits"]["afKinds7"] == {"faa": 0, "mange": 1}


# ── Alle tal er tal ─────────────────────────────────────────────────────────

def _walk_numbers_are_numbers(obj, path="ctx"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk_numbers_are_numbers(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_numbers_are_numbers(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        # rene tal som strenge ("72,3") er forbudt — formatering sker ved rendering
        assert not obj.replace(",", ".").replace(".", "", 1).lstrip("-").isdigit() or path.endswith(("mesoWeek", "id")), path


def test_full_context_against_real_plan_and_data_is_json():
    """Kører hele build_context mod rigtig plan.json + data.json (offline) og
    serialiserer til JSON uden fejl."""
    plan, data = _plan(), _data()
    today = date.fromisoformat(data["meta"]["updated"][:10])
    data["planTab"] = plan_tab.build_plan_tab(plan, None, data.get("week_sessions", []),
                                              data.get("all_weeks", {}), today,
                                              week_tss_actual=data.get("weekTssActual"))
    ctx = cc.build_context(plan, data, today, ctl=50.4, atl=51.1, tsb=-0.7, tss_actual=336)
    s = json.dumps(ctx, ensure_ascii=False)
    assert len(s) > 1000
    _walk_numbers_are_numbers(ctx)
    assert ctx["program"]["week"] == data["meta"]["week"]
    assert ctx["fitness"]["ctl"] == 50.4 and ctx["fitness"]["tsb"] == -0.7
    assert isinstance(ctx["rules"]["minHoursBetweenHaard"], int)
    assert ctx["week"]["tssActual"] == 336
    # søndag -> katalog og næste uge med, som data
    if today.weekday() == 6:
        assert ctx["catalog"] and all({"id", "min", "load"} <= set(w) for w in ctx["catalog"])
        assert ctx["nextWeek"] and ctx["nextWeek"]["programId"] == "tds-2027"
    # hash er stabil og uafhængig af nøgle-rækkefølge
    h1 = cc.inputs_hash(ctx)
    h2 = cc.inputs_hash(json.loads(s))
    assert h1 == h2 and len(h1) == 40


def test_entry_ids_collects_today_remaining_upcoming_and_next_week():
    plan = _plan()
    today = date(2026, 9, 8)
    data = {"planTab": plan_tab.build_plan_tab(plan, None, [], {}, today), "week_sessions": []}
    ctx = cc.build_context(plan, data, today, include_next_week=True)
    ids = cc.entry_ids(ctx)
    assert "6074cfa1" in ids                                  # Gang let 60 min 8/9
    assert any(u["date"] > "2026-09-08" for u in ctx["week"]["upcoming"])
    assert all(u["id"] in ids for u in ctx["week"]["upcoming"])
    assert ctx["today"]["sessions"][0]["name"] == "Gang let 60 min"
    assert ctx["today"]["sessions"][0]["done"] is False


def test_plan_tab_from_other_program_is_ignored():
    plan = _plan()
    today = date(2026, 9, 8)
    pt = plan_tab.build_plan_tab(plan, None, [], {}, date(2026, 9, 3))   # medoc-2026
    ctx = cc.build_context(plan, {"planTab": pt}, today)
    assert ctx["week"]["upcoming"] == [] and ctx["today"]["sessions"] == []
