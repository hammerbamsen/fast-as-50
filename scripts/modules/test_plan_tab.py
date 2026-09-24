# -*- coding: utf-8 -*-
"""Tests for plan_tab.py — Plan-fanens datalag (blok 4)."""
import json
import os
from datetime import date

import pytest

from modules import plan_tab
from modules import bike_library

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _plan():
    with open(os.path.join(_ROOT, "data", "plan.json"), encoding="utf-8") as fh:
        return json.load(fh)


# ── mesoWeek ────────────────────────────────────────────────────────────────

def test_meso_weeks_series_and_recovery():
    weeks = [
        {"week": 1, "blockType": "RECOVERY"},
        {"week": 2, "blockType": "RACE"},
        {"week": 3, "blockType": "BASE"},
        {"week": 4, "blockType": "BASE"},
        {"week": 5, "blockType": "RECOVERY"},
        {"week": 6, "blockType": "BASE"},
        {"week": 7, "blockType": "BASE"},
        {"week": 8, "blockType": "BASE"},
        {"week": 9, "blockType": "RECOVERY"},
    ]
    m = plan_tab.meso_weeks(weeks)
    assert m[1] == "R" and m[5] == "R" and m[9] == "R"
    assert m[2] == "1/1"            # RACE er sin egen serie
    assert m[3] == "1/2" and m[4] == "2/2"
    assert m[6] == "1/3" and m[7] == "2/3" and m[8] == "3/3"


def test_meso_weeks_real_plan_matches_purpose():
    prog = _plan()["programs"]["tds-2027"]
    m = plan_tab.meso_weeks(prog["weeks"])
    # purpose-teksterne i plan.json siger "Base 1/2" (uge 3, 6) og "Base 2/2" (uge 4, 7)
    assert m[3] == "1/2" and m[4] == "2/2" and m[6] == "1/2" and m[7] == "2/2"
    assert m[1] == "R" and m[5] == "R" and m[8] == "R"


# ── quotaUsed ───────────────────────────────────────────────────────────────

def test_quota_used_counts_library_bike_sessions_only():
    entries = [
        {"workout": {"type": "Ride"}, "libraryId": "test_ftp20"},        # haard
        {"workout": {"type": "Ride"}, "libraryId": "ss_3x15"},           # moderat
        {"workout": {"type": "Ride"}, "libraryId": "z2_grundtur_80"},    # let -> tælles ikke
        {"workout": {"type": "Ride", "name": "Cykel VO2 5x3"}},          # uden libraryId -> ignoreres
        {"workout": None, "libraryId": "tae_3x12"},                      # aflyst -> ignoreres
        {"workout": {"type": "Ride"}, "libraryId": "findes_ikke"},       # ukendt id -> ignoreres
    ]
    assert plan_tab.quota_used(entries) == {"haard": 1, "moderat": 1}


# ── load-heuristik ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("Løb Z2 45 min", "let"),
    ("Lang løb Z2 50 min", "let"),
    ("Gang let 60 min", "let"),
    ("Løb let 40 + 6 strides", "let"),
    ("Cykel Z2 60 min", "let"),
    ("Løb tempo 30 min", "moderat"),
    ("Cykel Z3 60 min", "moderat"),
    ("Løb VO2 5×3 min", "haard"),
    ("Løb målpace 4×3 min (1:30-tempo)", "haard"),
    ("CPH HALF — 21,1 km", "haard"),
    ("Cykel tærskel 2x20", "haard"),
])
def test_load_from_text(name, expected):
    assert plan_tab.load_from_text(name) == expected


def test_load_for_entry_prefers_library_and_strength_is_let():
    assert plan_tab.load_for_entry({"workout": {"type": "Ride", "name": "x"}, "libraryId": "tae_3x12"}) == "haard"
    assert plan_tab.load_for_entry({"workout": {"type": "WeightTraining", "name": "Styrke VO2 test"}}) == "let"
    # Svøm: beskrivelsens Z3-drills må ikke gøre passet moderat
    assert plan_tab.load_for_entry({"workout": {"type": "Swim", "name": "Svøm 2000m teknisk",
                                                 "description": "8x 100m moderat Z3"}}) == "let"


# ── hardSpacing ─────────────────────────────────────────────────────────────

def _sess(date_iso, eid, load, disc="bike"):
    return {"date": date_iso, "weekday": "Man", "entries": [
        {"id": eid, "name": eid, "disc": disc, "load": load, "mins": 60}]}


def test_hard_spacing_pairs_and_ok_flag():
    sessions = [{"week": 1, "days": [
        _sess("2026-09-21", "a", "haard"),
        _sess("2026-09-22", "b", "let"),
        _sess("2026-09-23", "c", "haard"),      # 48 t efter a -> ikke ok
        _sess("2026-09-26", "d", "haard"),      # 72 t efter c -> ok
    ]}]
    out = plan_tab.hard_spacing(sessions, 72)
    assert [(p["fromId"], p["toId"], p["hours"], p["ok"]) for p in out] == [
        ("a", "c", 48, False), ("c", "d", 72, True)]


def test_hard_spacing_ignores_extras_and_sorts_across_weeks():
    sessions = [
        {"week": 2, "days": [_sess("2026-09-28", "later", "haard")]},
        {"week": 1, "days": [
            _sess("2026-09-24", "first", "haard"),
            {"date": "2026-09-25", "weekday": "Fre", "entries": [
                {"id": None, "name": "ekstra", "disc": "run", "load": "haard", "extra": True}]},
        ]},
    ]
    out = plan_tab.hard_spacing(sessions)
    assert len(out) == 1
    assert out[0]["fromId"] == "first" and out[0]["toId"] == "later" and out[0]["hours"] == 96


# ── build_plan_tab mod den rigtige plan ─────────────────────────────────────

def test_build_plan_tab_window_spans_program_switch():
    plan = _plan()
    t = plan_tab.build_plan_tab(plan, None, [], {}, date(2026, 9, 6))
    assert t["programId"] == "medoc-2026"
    assert [(w["programId"], w["week"]) for w in t["weeks"][3:6]] == [
        ("medoc-2026", 13), ("medoc-2026", 14), ("tds-2027", 1)]
    # -4 uger bagud + hele tds-2027 (starter 7/9, 51 uger): 4 + 1 + 51 = 56 uger
    assert len(t["weeks"]) == 56
    assert t["weeks"][-1]["programId"] == "tds-2027" and t["weeks"][-1]["week"] == 51
    # sessions kun for uger med dage i plan.json (dage t.o.m. 1/11) — opslag på start
    assert len(t["sessions"]) < len(t["weeks"])
    assert all(any(w["start"] == s["start"] for w in t["weeks"]) for s in t["sessions"])
    empty = next(w for w in t["weeks"] if w["programId"] == "tds-2027" and w["week"] == 30)
    assert empty["hasDays"] is False and empty["blockType"]
    assert not any(s["start"] == empty["start"] for s in t["sessions"])
    assert all(len(s["days"]) == 7 for s in t["sessions"])
    assert t["ctl"]["window"]["to"] == "2026-10-25"
    cur = [w for w in t["weeks"] if w["isCurrent"]]
    assert len(cur) == 1 and cur[0]["week"] == 14
    # FTP-testen ligger i uge 5 (tor 8/10) efter forslag 2026-09-24; uge 3 er let
    w3 = next(w for w in t["weeks"] if w["programId"] == "tds-2027" and w["week"] == 3)
    assert w3["mesoWeek"] == "1/2" and w3["quota"] == {"haard": 0, "moderat": 0}
    assert w3["quotaUsed"] == {"haard": 0, "moderat": 0}
    w5 = next(w for w in t["weeks"] if w["programId"] == "tds-2027" and w["week"] == 5)
    assert w5["quota"] == {"haard": 1, "moderat": 0} and w5["quotaUsed"] == {"haard": 1, "moderat": 0}
    assert "FaF 0 Test - FTP 20 min" in w5["keySessions"]
    # Kælderpas bærer bibliotekets navn, ERG og formål
    s5 = next(s for s in t["sessions"] if s["programId"] == "tds-2027" and s["week"] == 5)
    ftp = next(e for d in s5["days"] for e in d["entries"] if e["libraryId"] == "test_ftp20")
    assert ftp["erg"] is False and ftp["load"] == "haard" and ftp["isKey"] and ftp["zwiftName"] == "FaF 0 Test - FTP 20 min"
    # CPH Half som race -> haard/nøglepas, og ugen bærer løbet
    w2 = next(w for w in t["weeks"] if w["programId"] == "tds-2027" and w["week"] == 2)
    assert w2["races"][0]["name"] == "CPH Half"
    assert len(t["ctl"]["history"]) == 12
    assert [p["name"] for p in t["ctl"]["phases"]][3:5] == ["TAPER", "RACE"]


def test_build_plan_tab_actuals_and_tss_from_intervals():
    plan = _plan()
    week_sessions = [
        {"day": "Man", "disc": "strength", "label": "Styrke 25 min overkrop + core", "done": True,
         "actual_tss": 5, "actual_mins": 20, "completion": "done"},
        {"day": "Man", "disc": "walk", "label": "København Gang", "done": True, "extra": True,
         "actual_tss": 10, "actual_mins": 49},
    ]
    t = plan_tab.build_plan_tab(plan, None, week_sessions, {}, date(2026, 9, 6),
                                week_tss_actual={"14": 348, "13": 320})
    cur = next(w for w in t["weeks"] if w["isCurrent"])
    assert cur["tssActual"] == 348
    prev = next(w for w in t["weeks"] if w["week"] == 13)
    assert prev["tssActual"] == 320
    nxt = next(w for w in t["weeks"] if w["programId"] == "tds-2027")
    assert nxt["tssActual"] is None
    mon = next(s for s in t["sessions"] if s["week"] == 14)["days"][0]
    planned = [e for e in mon["entries"] if not e.get("extra")]
    extra = [e for e in mon["entries"] if e.get("extra")]
    assert planned[0]["done"] is True and planned[0]["actualMins"] == 20
    assert extra and extra[0]["name"] == "København Gang"


def test_build_plan_tab_ctl_history_and_projection_guard():
    plan = _plan()
    ctl_daily = {"2026-09-06": 50.4, "2026-08-30": 50.7, "2026-08-22": 52.0}
    view = {"kennet": {"programId": "andet-program", "projection": [{"d": "2026-09-07", "ctl": 50}]}}
    t = plan_tab.build_plan_tab(plan, view, [], {}, date(2026, 9, 6), ctl_daily=ctl_daily)
    h = t["ctl"]["history"]
    assert h[-1]["ctl"] == 50.4 and h[-2]["ctl"] == 50.7
    assert h[-3]["ctl"] == 52.0          # søndag 23/8 mangler -> seneste kendte i ugen (22/8)
    assert t["ctl"]["projection"] == []  # programId matcher ikke -> ingen projektion
    view["kennet"]["programId"] = "medoc-2026"
    t2 = plan_tab.build_plan_tab(plan, view, [], {}, date(2026, 9, 6), ctl_daily=ctl_daily)
    assert t2["ctl"]["projection"] == [{"d": "2026-09-07", "ctl": 50.0}]
