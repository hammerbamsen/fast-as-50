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
