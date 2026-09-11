"""Blok 10: 14-dages check-in + automatisk styrke-progression."""
import json
from datetime import date

from . import strength_progression as sp
from . import edit_apply
from . import body

EX_A = [{"name": "Thruster", "load": "2×5 kg DB", "reps": 10, "unit": "reps", "group": "ben"},
        {"name": "Renegade row", "load": "10 kg DB", "reps": 8, "unit": "reps/side", "group": "core"},
        {"name": "KB swing", "load": "12,5 kg KB", "reps": 15, "unit": "reps", "group": "ben"},
        {"name": "KB row", "load": "10 kg DB", "reps": 10, "unit": "reps/side", "group": "overkrop"},
        {"name": "Press", "load": "2×5 kg DB", "reps": 10, "unit": "reps", "group": "overkrop"}]
EX_B = [{"name": "RDL", "load": "12,5 kg KB", "reps": 12, "unit": "reps", "group": "ben"},
        {"name": "Split squat", "load": "12,5 kg KB goblet", "reps": 8, "unit": "reps/ben", "group": "ben"},
        {"name": "Farmers walk", "load": "2×10 kg DB", "reps": 40, "unit": "m", "group": "core"}]


def test_step_load_ladders_and_cap():
    assert sp.step_load("2×5 kg DB", 1) == ("2×7 kg DB", False)
    assert sp.step_load("12,5 kg KB", 1) == ("16 kg KB", False)
    assert sp.step_load("12,5 kg KB goblet", 2) == ("20 kg KB goblet", False)
    assert sp.step_load("12,5 kg KB", 5) == ("20 kg KB", True)          # loft = hjemme-gym
    assert sp.step_load("10 kg DB", 2) == ("15 kg DB", False)
    assert sp.step_load("øvelse uden kg", 3) == ("øvelse uden kg", False)
    assert sp.step_load("2×5 kg DB", 0) == ("2×5 kg DB", False)


def test_apply_state_ben_upper_core():
    st = {"ben": {"step": 1}, "overkrop": {"step": 0, "extraReps": 2}}
    out = sp.apply_state(EX_A, st)
    by = {e["name"]: e for e in out}
    assert by["Thruster"]["load"] == "2×7 kg DB" and by["Thruster"]["reps"] == 10
    assert by["KB swing"]["load"] == "16 kg KB"
    assert by["Press"]["load"] == "2×5 kg DB" and by["Press"]["reps"] == 12       # +2 reps
    assert by["KB row"]["reps"] == 12 and by["KB row"]["load"] == "10 kg DB"
    assert by["Renegade row"]["reps"] == 10                                     # core = overkrop
    assert by["Thruster"]["baseLoad"] == "2×5 kg DB"
    outb = sp.apply_state(EX_B, st)
    assert outb[2]["reps"] == 40 and outb[2]["unit"] == "m"                      # meter får ikke +reps


def test_advance_rules():
    s0 = sp.empty_state()
    s1 = sp.advance(s0, True, True)
    assert s1 == {"ben": {"step": 1}, "overkrop": {"step": 0, "extraReps": 2}}
    s2 = sp.advance(s1, False, True)
    assert s2["overkrop"] == {"step": 0, "extraReps": 4} and s2["ben"]["step"] == 1
    s3 = sp.advance(s2, False, True)
    assert s3["overkrop"] == {"step": 1, "extraReps": 0}                       # +4 nået -> vægt op, reps ned
    assert sp.advance(s3, False, False) == s3


def _days(recovery_week_mon=None):
    days = []
    for d in ("2026-09-28", "2026-10-05", "2026-10-08", "2026-10-12", "2026-10-15"):
        note = "recovery: 2 runder, ingen progression" if recovery_week_mon and "2026-10-05" <= d <= "2026-10-11" else ""
        days.append({"date": d, "entries": [{"id": "s" + d, "note": note,
                     "templateId": "styrke-fs4-a-2r",
                     "workout": {"name": "Styrke A · Functional 4 · 2 runder", "type": "WeightTraining"}}]})
    return days


def test_apply_checkin_recovery_defers_effective_from():
    prog = sp.apply_checkin(None, "2026-10-04", True, False, _days(recovery_week_mon=True))
    assert prog["effectiveFrom"] == "2026-10-12" and prog["lastCheckin"] == "2026-10-04"
    assert prog["current"]["ben"]["step"] == 1 and prog["previous"]["ben"]["step"] == 0
    assert sp.state_for_date(prog, "2026-10-08")["ben"]["step"] == 0            # recovery-uge: uændret
    assert sp.state_for_date(prog, "2026-10-12")["ben"]["step"] == 1
    prog2 = sp.apply_checkin(None, "2026-10-04", True, False, _days())
    assert prog2["effectiveFrom"] == "2026-10-05"


def test_build_checkin_due_and_answered():
    ck = sp.build_checkin({}, None, date(2026, 10, 3))
    assert ck["due"] is False and ck["date"] is None and ck["next"] == "2026-10-04"
    ck = sp.build_checkin({}, None, date(2026, 10, 4))
    assert ck["due"] is True and ck["date"] == "2026-10-04" and ck["next"] == "2026-11-01"
    ck = sp.build_checkin({}, None, date(2026, 10, 9))                          # ubesvaret bliver stående
    assert ck["due"] is True and ck["date"] == "2026-10-04"
    ck = sp.build_checkin({"2026-10-04": {"legs": 1, "upper": 1}}, None, date(2026, 10, 9))
    assert ck["due"] is False and ck["last"]["legs"] == 1
    ck = sp.build_checkin({"2026-10-04": {"legs": 1, "upper": 1}}, None, date(2026, 11, 1))
    assert ck["due"] is True and ck["date"] == "2026-11-01"
    assert ck["question"].startswith("Alle runder")


def _plan():
    return {"athletes": {"kennet": {"days": _days(recovery_week_mon=True)}}}


def test_edit_apply_strength_checkin_writes_both_blocks():
    res = edit_apply.apply_edit(json.dumps(_plan()), "strength_checkin", "chk:2026-10-04",
                                {"legs": 1, "upper": 1}, athlete="kennet")
    assert res["status"] == "ok" and res["dates_changed"] == [] and res["gate"]["msg"] == "Check-in gemt"
    new = json.loads(res["new_plan_raw"])
    ath = new["athletes"]["kennet"]
    assert ath["strengthCheckin"]["2026-10-04"]["legs"] == 1 and ath["strengthCheckin"]["2026-10-04"]["at"].endswith("Z")
    assert ath["strengthProgression"]["current"] == {"ben": {"step": 1}, "overkrop": {"step": 0, "extraReps": 2}}
    assert ath["strengthProgression"]["effectiveFrom"] == "2026-10-12"
    # andet check-in bygger videre
    res2 = edit_apply.apply_edit(res["new_plan_raw"], "strength_checkin", "chk:2026-11-01",
                                 {"legs": 0, "upper": 1}, athlete="kennet")
    p2 = json.loads(res2["new_plan_raw"])["athletes"]["kennet"]["strengthProgression"]
    assert p2["current"] == {"ben": {"step": 1}, "overkrop": {"step": 0, "extraReps": 4}}
    assert p2["previous"]["overkrop"]["extraReps"] == 2 and p2["effectiveFrom"] == "2026-11-02"


def test_edit_apply_strength_checkin_validation():
    import pytest
    with pytest.raises(ValueError):
        edit_apply.apply_edit(json.dumps(_plan()), "strength_checkin", "chk:nope", {"legs": 1, "upper": 1})
    with pytest.raises(ValueError):
        edit_apply.apply_edit(json.dumps(_plan()), "strength_checkin", "chk:2026-10-04", {"legs": 2, "upper": 1})


def test_build_strength_next_has_progressed_exercises_and_checkin():
    tpls = [{"id": "styrke-fs4-a-2r", "name": "Styrke A · Functional 4 · 2 runder", "type": "WeightTraining",
             "rounds": 2, "exercises": EX_A, "progression": "x"}]
    plan = _plan()
    plan["athletes"]["kennet"]["strengthProgression"] = {
        "current": {"ben": {"step": 1}, "overkrop": {"step": 0, "extraReps": 2}},
        "previous": sp.empty_state(), "effectiveFrom": "2026-10-12", "lastCheckin": "2026-10-04"}
    plan["athletes"]["kennet"]["strengthCheckin"] = {"2026-10-04": {"legs": 1, "upper": 1}}
    s = body.build_strength(plan, {"from": "2026-09-08", "to": "2026-10-06", "sessions": []},
                            today=date(2026, 10, 6), templates=tpls)
    nx = s["next"]
    assert nx["date"] == "2026-10-08" and nx["recovery"] is True
    assert nx["exercises"][0]["load"] == "2×5 kg DB" and nx["stateSummary"] == "Ben grundvægt · Overkrop grundvægt"
    s2 = body.build_strength(plan, {"from": "2026-09-08", "to": "2026-10-13", "sessions": []},
                             today=date(2026, 10, 13), templates=tpls)
    nx2 = s2["next"]
    assert nx2["date"] == "2026-10-15" and nx2["recovery"] is False
    assert nx2["exercises"][0]["load"] == "2×7 kg DB" and nx2["exercises"][4]["reps"] == 12
    assert nx2["stateSummary"] == "Ben trin 1 · Overkrop grundvægt +2 reps"
    assert s2["checkin"]["due"] is False and s2["checkin"]["next"] == "2026-11-01"
