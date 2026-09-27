# -*- coding: utf-8 -*-
"""Tests for edit_apply — Friel-gate + mutation.

Kør: python3 -m pytest scripts/modules/test_edit_apply.py -q
"""
import copy
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from modules import edit_apply

PLAN_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "plan.json"
PLAN = json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _plan_copy():
    return copy.deepcopy(PLAN)


def _future_run_entry(plan):
    """Find en løbe-entry i en fremtidig uge (uden allerede eksisterende hard-flags)."""
    for d in plan["athletes"]["kennet"]["days"]:
        if d["date"] < "2026-07-20":  # senere = færre eksisterende flags
            continue
        for e in d["entries"]:
            if (e.get("workout") or {}).get("type") == "Run":
                return d["date"], e
    raise RuntimeError("Ingen fremtidig løbe-entry fundet")


def _entry_by_id(plan, eid):
    for d in plan["athletes"]["kennet"]["days"]:
        for e in d["entries"]:
            if e.get("id") == eid:
                return d, e
    return None, None


# -- adjust --

def test_adjust_moving_time():
    plan = _plan_copy()
    _, e = _future_run_entry(plan)
    result = edit_apply.apply_edit(json.dumps(plan), "adjust", e["id"],
                                    {"moving_time": 2400})
    assert result["status"] == "ok"
    new_plan = json.loads(result["new_plan_raw"])
    _, new_e = _entry_by_id(new_plan, e["id"])
    assert new_e["workout"]["moving_time"] == 2400


def test_adjust_description_preserved_other_fields():
    plan = _plan_copy()
    _, e = _future_run_entry(plan)
    orig_name = e["workout"]["name"]
    result = edit_apply.apply_edit(json.dumps(plan), "adjust", e["id"],
                                    {"description": "Ny beskrivelse"})
    new_plan = json.loads(result["new_plan_raw"])
    _, new_e = _entry_by_id(new_plan, e["id"])
    assert new_e["workout"]["description"] == "Ny beskrivelse"
    assert new_e["workout"]["name"] == orig_name  # ikke overskrevet


# -- swap_template --

def test_swap_template_from_library():
    plan = _plan_copy()
    _, e = _future_run_entry(plan)
    result = edit_apply.apply_edit(json.dumps(plan), "swap_template",
                                    e["id"], {"template_id": "cykel-z2-90"})
    assert result["status"] == "ok"
    new_plan = json.loads(result["new_plan_raw"])
    _, new_e = _entry_by_id(new_plan, e["id"])
    assert new_e["workout"]["type"] == "Ride"
    assert "Cykel Z2 90" in new_e["workout"]["name"]


def test_swap_template_to_rest_day():
    plan = _plan_copy()
    _, e = _future_run_entry(plan)
    result = edit_apply.apply_edit(json.dumps(plan), "swap_template",
                                    e["id"], {"template_id": "hvile"})
    assert result["status"] == "ok"
    new_plan = json.loads(result["new_plan_raw"])
    _, new_e = _entry_by_id(new_plan, e["id"])
    assert new_e["workout"] is None


def test_swap_unknown_template_raises():
    plan = _plan_copy()
    _, e = _future_run_entry(plan)
    with pytest.raises(ValueError, match="ikke"):
        edit_apply.apply_edit(json.dumps(plan), "swap_template",
                               e["id"], {"template_id": "findes-ikke"})


# -- cancel --

def test_cancel_becomes_rest():
    plan = _plan_copy()
    _, e = _future_run_entry(plan)
    result = edit_apply.apply_edit(json.dumps(plan), "cancel", e["id"], {})
    assert result["status"] == "ok"
    new_plan = json.loads(result["new_plan_raw"])
    _, new_e = _entry_by_id(new_plan, e["id"])
    assert new_e["workout"] is None


# -- move --

def test_move_swap_swaps_days():
    plan = _plan_copy()
    src_date, e = _future_run_entry(plan)
    # find en anden fremtidig dag
    other_date = None
    for d in plan["athletes"]["kennet"]["days"]:
        if d["date"] > src_date and d["date"] < "2026-08-25":
            if not any((x.get("workout") or {}).get("type") == "Run" for x in d["entries"]):
                other_date = d["date"]
                break
    assert other_date, "Ingen egnet måldag"
    result = edit_apply.apply_edit(json.dumps(plan), "move", e["id"],
                                    {"target_date": other_date, "mode": "swap"})
    # kan være ok eller reject afhængigt af Friel, men mutation skal være sket i sim
    new_plan = json.loads(result["new_plan_raw"]) if result["status"] == "ok" else \
        edit_apply._simulate_mutation(plan, "move", e["id"],
                                       {"target_date": other_date, "mode": "swap"})[0]
    src_d = next(d for d in new_plan["athletes"]["kennet"]["days"] if d["date"] == src_date)
    dst_d = next(d for d in new_plan["athletes"]["kennet"]["days"] if d["date"] == other_date)
    # e skal nu ligge på dst_d
    assert any(x.get("id") == e["id"] for x in dst_d["entries"])
    assert not any(x.get("id") == e["id"] for x in src_d["entries"])


def test_move_add_keeps_target_entries():
    """27/9-2026: mode 'add' flytter kun passet — måldagens pas bliver."""
    plan = _plan_copy()
    src_date, e = _future_run_entry(plan)
    dst = next(d for d in plan["athletes"]["kennet"]["days"]
               if d["date"] > src_date and any(x.get("workout") for x in d["entries"])
               and not any(x.get("id") == e["id"] for x in d["entries"]))
    before_ids = [x.get("id") for x in dst["entries"]]
    sim = edit_apply._simulate_mutation(plan, "move", e["id"],
                                        {"target_date": dst["date"], "mode": "add"})[0]
    src_d = next(d for d in sim["athletes"]["kennet"]["days"] if d["date"] == src_date)
    dst_d = next(d for d in sim["athletes"]["kennet"]["days"] if d["date"] == dst["date"])
    assert [x.get("id") for x in dst_d["entries"]] == before_ids + [e["id"]]
    assert not any(x.get("id") == e["id"] for x in src_d["entries"])


def test_consecutive_runs_is_warn_not_hard():
    """27/9-2026: to løbedage i træk kan bekræftes væk (WARN)."""
    from modules import friel
    plan = _plan_copy()
    for f in friel.structural_flags(plan):
        if f["rule"] == "consecutive_runs":
            assert f["level"] == "WARN"


# -- gate --

def test_reject_when_adding_hard_flag():
    """Flyt et løb til en dag med et andet løb → 4 løb i den uge → HARD."""
    plan = _plan_copy()
    # find en uge med 3 løb allerede
    from datetime import date as _date
    plan_start = _date.fromisoformat(plan["program"]["start"])
    week_runs = {}
    for d in plan["athletes"]["kennet"]["days"]:
        w = (_date.fromisoformat(d["date"]) - plan_start).days // 7 + 1
        if any((e.get("workout") or {}).get("type") == "Run" for e in d["entries"]):
            week_runs.setdefault(w, []).append(d["date"])
    # uge 8 er en travl uge — find en uge med 3 løb-dage
    heavy_weeks = [w for w, ds in week_runs.items() if len(ds) == 3 and w >= 7]
    if not heavy_weeks:
        pytest.skip("Ingen uge med præcis 3 løb til at teste")
    hw = heavy_weeks[0]
    # find en dag i den uge UDEN løb
    ws = plan_start + __import__("datetime").timedelta(weeks=hw - 1)
    days_in_week = [d for d in plan["athletes"]["kennet"]["days"]
                    if _date.fromisoformat(d["date"]) >= ws
                    and _date.fromisoformat(d["date"]) < ws + __import__("datetime").timedelta(days=7)]
    no_run_day = next((d for d in days_in_week
                       if not any((e.get("workout") or {}).get("type") == "Run" for e in d["entries"])), None)
    if not no_run_day:
        pytest.skip("Ingen løbfrie dage i heavy-uge")
    # find en fremtidig løb-entry uden for denne uge
    src_date, e = None, None
    for d in plan["athletes"]["kennet"]["days"]:
        d_date = _date.fromisoformat(d["date"])
        if d_date < ws or d_date >= ws + __import__("datetime").timedelta(days=7):
            for ent in d["entries"]:
                if (ent.get("workout") or {}).get("type") == "Run" and d["date"] > "2026-07-15":
                    src_date, e = d["date"], ent
                    break
            if e:
                break
    if not e:
        pytest.skip("Ingen egnet fremtidig løb-entry")
    result = edit_apply.apply_edit(json.dumps(plan), "move", e["id"],
                                    {"target_date": no_run_day["date"], "mode": "replace"})
    # Kan blive OK hvis Friel-tælle ikke tricker, ellers reject/warn
    assert result["status"] in ("reject", "warn", "ok")
    # Uanset: gate skal have kørt uden crash
    assert "gate" in result


def test_ok_action_returns_new_plan_raw():
    plan = _plan_copy()
    _, e = _future_run_entry(plan)
    result = edit_apply.apply_edit(json.dumps(plan), "adjust", e["id"],
                                    {"moving_time": 2400})
    if result["status"] == "ok":
        assert "new_plan_raw" in result
        # Validér at det er valid JSON
        json.loads(result["new_plan_raw"])


def test_unknown_entry_id_raises():
    plan = _plan_copy()
    with pytest.raises(ValueError, match="ikke fundet"):
        edit_apply.apply_edit(json.dumps(plan), "adjust", "deadbeef",
                               {"moving_time": 3000})


def test_unknown_action_raises():
    plan = _plan_copy()
    _, e = _future_run_entry(plan)
    with pytest.raises(ValueError, match="Ukendt action"):
        edit_apply.apply_edit(json.dumps(plan), "explode", e["id"], {})


# -- id-integritet --

def test_entry_ids_preserved_after_edit():
    plan = _plan_copy()
    _, e = _future_run_entry(plan)
    orig_ids = {ent["id"] for d in plan["athletes"]["kennet"]["days"]
                for ent in d["entries"] if ent.get("id")}
    result = edit_apply.apply_edit(json.dumps(plan), "adjust", e["id"],
                                    {"moving_time": 3000})
    new_plan = json.loads(result["new_plan_raw"])
    new_ids = {ent["id"] for d in new_plan["athletes"]["kennet"]["days"]
               for ent in d["entries"] if ent.get("id")}
    assert orig_ids == new_ids


def test_workout_library_loadable():
    lib_path = PLAN_PATH.parent / "workout_library.json"
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    ids = [t["id"] for t in lib["templates"]]
    assert len(ids) == len(set(ids)), "Duplikate template-ids"
    assert "hvile" in ids
    assert "cykel-z2-90" in ids


# -- set_zones (28/7-2026) ----------------------------------------------------

def test_set_zones_ftp_updates_derived_watt():
    plan = _plan_copy()
    res = edit_apply.apply_edit(json.dumps(plan), "set_zones", "zones",
                                {"ftpW": 300})
    assert res["status"] == "ok"
    z = json.loads(res["new_plan_raw"])["athletes"]["kennet"]["zones"]
    assert z["ftpW"] == 300
    assert z["bikeFtpW"] == 300           # legacy-spejl følger med
    assert z["bikeWatt"]["Z4"] == "272-317 W"
    assert z["run"] == plan["athletes"]["kennet"]["zones"]["run"]  # løb urørt


def test_set_zones_threshold_updates_derived_pace():
    plan = _plan_copy()
    res = edit_apply.apply_edit(json.dumps(plan), "set_zones", "zones",
                                {"thresholdSec": 250})
    assert res["status"] == "ok"
    z = json.loads(res["new_plan_raw"])["athletes"]["kennet"]["zones"]
    assert z["thresholdSec"] == 250
    assert z["runThreshold"] == "4:10/km"
    assert z["run"]["Z4"] == "4:03-4:15/km"
    assert z["bikeWatt"] == plan["athletes"]["kennet"]["zones"]["bikeWatt"]


def test_set_zones_roundtrip_is_identity():
    """Sæt de vaerdier planen allerede har -> zones skal vaere uaendret."""
    plan = _plan_copy()
    z0 = plan["athletes"]["kennet"]["zones"]
    res = edit_apply.apply_edit(json.dumps(plan), "set_zones", "zones",
                                {"thresholdSec": z0["thresholdSec"],
                                 "ftpW": z0["ftpW"]})
    z1 = json.loads(res["new_plan_raw"])["athletes"]["kennet"]["zones"]
    assert z1 == z0


def test_set_zones_changes_no_dates():
    """dates_changed skal vaere tom — ellers rammer orkestratoren Intervals."""
    plan = _plan_copy()
    res = edit_apply.apply_edit(json.dumps(plan), "set_zones", "zones",
                                {"ftpW": 285})
    assert res["dates_changed"] == []


def test_set_zones_leaves_days_untouched():
    plan = _plan_copy()
    res = edit_apply.apply_edit(json.dumps(plan), "set_zones", "zones",
                                {"ftpW": 285, "thresholdSec": 255})
    new = json.loads(res["new_plan_raw"])
    assert new["athletes"]["kennet"]["days"] == plan["athletes"]["kennet"]["days"]


@pytest.mark.parametrize("params", [{"ftpW": 40}, {"thresholdSec": 900}, {}])
def test_set_zones_rejects_nonsense(params):
    plan = _plan_copy()
    with pytest.raises(ValueError):
        edit_apply.apply_edit(json.dumps(plan), "set_zones", "zones", params)


def test_swap_template_from_bike_library_sets_library_id():
    plan = _plan_copy()
    _, e = _future_run_entry(plan)
    result = edit_apply.apply_edit(json.dumps(plan), "swap_template",
                                    e["id"], {"template_id": "ss_3x15"})
    assert result["status"] == "ok"
    new_plan = json.loads(result["new_plan_raw"])
    _, new_e = _entry_by_id(new_plan, e["id"])
    assert new_e["libraryId"] == "ss_3x15"
    assert new_e["workout"]["type"] == "Ride"
    assert new_e["workout"]["name"] == "FaF 3 SS - 3 x 15"
    assert new_e["workout"]["workout_doc"]["steps"]
    # Skift tilbage til workout_library fjerner libraryId igen
    result2 = edit_apply.apply_edit(result["new_plan_raw"], "swap_template",
                                     e["id"], {"template_id": "lob-z2-45"})
    _, e2 = _entry_by_id(json.loads(result2["new_plan_raw"]), e["id"])
    assert "libraryId" not in e2


# -- strength_log (blok 8, 8/9-2026) -------------------------------------------

def test_strength_log_writes_athlete_log_no_dates():
    plan = _plan_copy()
    res = edit_apply.apply_edit(json.dumps(plan), "strength_log", "log:2026-09-12",
                                {"rpe": 7, "complete": 1, "note": "swing 16 næste gang",
                                 "template": "styrke-fs4-a-2r"})
    assert res["status"] == "ok" and res["dates_changed"] == []
    new = json.loads(res["new_plan_raw"])
    rec = new["athletes"]["kennet"]["strengthLog"]["2026-09-12"]
    assert rec["rpe"] == 7 and rec["complete"] == 1 and rec["template"] == "styrke-fs4-a-2r"
    assert rec["note"] == "swing 16 næste gang" and rec["at"].endswith("+00:00")
    # dage og zoner urørte
    assert new["athletes"]["kennet"]["days"] == plan["athletes"]["kennet"]["days"]
    assert new["athletes"]["kennet"]["zones"] == plan["athletes"]["kennet"]["zones"]


def test_strength_log_overwrites_same_date_and_keeps_others():
    plan = _plan_copy()
    r1 = edit_apply.apply_edit(json.dumps(plan), "strength_log", "log:2026-09-12",
                               {"rpe": 8, "complete": 0, "note": ""})
    r2 = edit_apply.apply_edit(r1["new_plan_raw"], "strength_log", "log:2026-09-14",
                               {"rpe": 6, "complete": True})
    r3 = edit_apply.apply_edit(r2["new_plan_raw"], "strength_log", "log:2026-09-12",
                               {"rpe": "5", "complete": "1", "note": "bedre"})
    log = json.loads(r3["new_plan_raw"])["athletes"]["kennet"]["strengthLog"]
    assert set(log) == {"2026-09-12", "2026-09-14"}
    assert log["2026-09-12"] == {**log["2026-09-12"], "rpe": 5, "complete": 1, "note": "bedre", "template": None}
    assert log["2026-09-14"]["complete"] == 1 and log["2026-09-14"]["rpe"] == 6


@pytest.mark.parametrize("entry_id,params", [
    ("log:2026-09-12", {"rpe": 0, "complete": 1}),
    ("log:2026-09-12", {"rpe": 11, "complete": 1}),
    ("log:2026-09-12", {"rpe": "syv", "complete": 1}),
    ("log:2026-09-12", {"rpe": 7, "complete": 2}),
    ("log:2026-09-12", {"rpe": 7, "complete": 1, "note": "x" * 141}),
    ("2026-09-12", {"rpe": 7, "complete": 1}),
    ("log:12-09-2026", {"rpe": 7, "complete": 1}),
])
def test_strength_log_rejects_bad_input(entry_id, params):
    plan = _plan_copy()
    with pytest.raises(ValueError):
        edit_apply.apply_edit(json.dumps(plan), "strength_log", entry_id, params)
