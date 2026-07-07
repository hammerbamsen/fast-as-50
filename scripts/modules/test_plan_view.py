# -*- coding: utf-8 -*-
"""Tests for plan_view.compute og inputs_hash. Kør: pytest scripts/modules/test_plan_view.py"""
import json
from datetime import date, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import plan_view

PLAN = json.loads(
    (Path(__file__).resolve().parent.parent.parent / "data" / "plan.json")
    .read_text(encoding="utf-8"))

SEED = dict(seed_ctl=46.8, seed_atl=57.4, seed_date="2026-07-07")


def test_compute_shape():
    v = plan_view.compute(PLAN, **SEED)
    assert set(v) == {"generated", "kennet"}
    k = v["kennet"]
    assert k["seed"] == {"date": "2026-07-07", "ctl": 46.8, "atl": 57.4}
    assert len(k["weeks"]) == PLAN["program"]["totalWeeks"]
    assert isinstance(k["projection"], list) and k["projection"]


def test_projection_runs_to_plan_end():
    v = plan_view.compute(PLAN, **SEED)
    proj = v["kennet"]["projection"]
    start = date.fromisoformat(PLAN["program"]["start"])
    plan_end = start + timedelta(weeks=PLAN["program"]["totalWeeks"])
    assert proj[0]["d"] == "2026-07-08"          # dagen efter seed
    assert proj[-1]["d"] == str(plan_end - timedelta(days=1))
    for p in proj:
        assert isinstance(p["ctl"], float) and isinstance(p["tsb"], float)


def test_deviation_is_proj_minus_target():
    v = plan_view.compute(PLAN, **SEED)
    targets = {w["week"]: w["ctlTarget"] for w in PLAN["weeks"]}
    checked = 0
    for w in v["kennet"]["weeks"]:
        if w["projEndCtl"] is not None:
            assert abs(w["deviation"] - round(w["projEndCtl"] - targets[w["week"]], 1)) < 0.05
            checked += 1
    assert checked >= 8   # de fleste uger ligger efter seed-datoen


def test_week_flags_match_flat_list():
    v = plan_view.compute(PLAN, **SEED)
    flat = v["kennet"]["flags"]
    per_week = [f for w in v["kennet"]["weeks"] for f in w["flags"]]
    key = lambda f: (f["week"], f["rule"], f["msg"])
    assert sorted(map(key, flat)) == sorted(map(key, per_week))


def test_flags_serializable_and_levels_valid():
    v = plan_view.compute(PLAN, **SEED)
    json.dumps(v, ensure_ascii=False)
    for f in v["kennet"]["flags"]:
        assert f["level"] in ("HARD", "WARN")
        assert isinstance(f["historic"], bool)


def test_hash_stable_and_sensitive():
    raw = json.dumps(PLAN, ensure_ascii=False)
    h1 = plan_view.inputs_hash(raw, 46.8, 57.4, "2026-07-07")
    h2 = plan_view.inputs_hash(raw, 46.8, 57.4, "2026-07-07")
    h3 = plan_view.inputs_hash(raw, 47.1, 57.4, "2026-07-07")
    h4 = plan_view.inputs_hash(raw + " ", 46.8, 57.4, "2026-07-07")
    assert h1 == h2 and h1 != h3 and h1 != h4


def test_entry_ids_present_and_unique():
    ids = [e["id"]
           for a in PLAN["athletes"].values()
           for d in a["days"] for e in d["entries"]]
    assert ids and len(ids) == len(set(ids))
    assert all(len(i) == 8 for i in ids)
