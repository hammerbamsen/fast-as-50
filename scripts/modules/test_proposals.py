# -*- coding: utf-8 -*-
"""Tests for proposals + edit_apply apply_proposal/reject_proposal (blok 9).

Kør: python3 -m pytest scripts/modules/test_proposals.py -q
"""
import copy
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from datetime import date
from modules import bike_library, edit_apply, proposals

ROOT = Path(__file__).resolve().parent.parent.parent
PLAN = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))
REAL_PROPOSAL = ROOT / "data" / "proposals" / "2026-09-07-uge3-8.json"


def _plan():
    return copy.deepcopy(PLAN)


def _day(plan, d_iso, athlete="kennet"):
    return next((d for d in plan["athletes"][athlete]["days"] if d["date"] == d_iso), None)


def _future_free_dates(plan, n=2, after="2026-10-25"):
    """Fremtidige datoer uden done-entries (planen slutter 1/11-2026 -> uge 8)."""
    out = []
    for d in plan["athletes"]["kennet"]["days"]:
        if d["date"] > after and not any(e.get("done") for e in d["entries"]):
            out.append(d["date"])
        if len(out) >= n:
            break
    assert len(out) >= n
    return out


def _styrke(tid="styrke-fs4-a-2r", note="test"):
    t = edit_apply._find_template(tid)
    return {"workout": {"name": t["name"], "type": t["type"],
                        "moving_time": t["moving_time"], "description": t["description"]},
            "templateId": tid, "note": note}


def _prop(changes, pid="t-1", status="pending"):
    return {"id": pid, "createdAt": "2026-09-09T10:00:00Z", "createdBy": "test",
            "title": "Test", "note": "n", "summary": ["s"], "status": status,
            "decidedAt": None, "result": None, "changes": changes}


# -- apply_changes (ren) -------------------------------------------------------

def test_set_day_replaces_entries_and_generates_unique_ids():
    plan = _plan()
    d1, d2 = _future_free_dates(plan)
    sim, dates = proposals.apply_changes(plan, [
        {"date": d1, "action": "set_day", "entries": [_styrke(), _styrke("styrke-fs4-b-2r")]},
        {"date": d2, "action": "set_day", "entries": []},
    ])
    assert dates == [d1, d2]
    assert [e["templateId"] for e in _day(sim, d1)["entries"]] == ["styrke-fs4-a-2r", "styrke-fs4-b-2r"]
    assert _day(sim, d2)["entries"] == []
    ids = [e["id"] for d in sim["athletes"]["kennet"]["days"] for e in d["entries"]]
    assert len(ids) == len(set(ids))
    assert all(len(e["id"]) == 8 for e in _day(sim, d1)["entries"])
    # input urørt
    assert _day(plan, d2)["entries"] == _day(PLAN, d2)["entries"]


def test_set_day_keeps_done_entries():
    plan = _plan()
    d1, = _future_free_dates(plan, 1)
    day = _day(plan, d1)
    day["entries"].insert(0, {"id": "deadbee1", "workout": {"name": "Gjort", "type": "Run"}, "done": True})
    sim, _ = proposals.apply_changes(plan, [{"date": d1, "action": "set_day", "entries": [_styrke()]}])
    ents = _day(sim, d1)["entries"]
    assert ents[0]["id"] == "deadbee1" and ents[0]["done"] is True
    assert ents[1]["templateId"] == "styrke-fs4-a-2r"


def test_set_day_reuses_id_for_unchanged_workout():
    """Kun note ændret på et kælderpas -> samme entry-id (ingen churn i Intervals/Outlook-historik)."""
    plan = _plan()
    d_iso, e = next((d["date"], e) for d in plan["athletes"]["kennet"]["days"]
                    if d["date"] > "2026-10-25"
                    for e in d["entries"] if e.get("libraryId"))
    spec = {k: v for k, v in e.items() if k != "id"}
    spec["note"] = "ny note"
    sim, _ = proposals.apply_changes(plan, [{"date": d_iso, "action": "set_day", "entries": [spec]}])
    new = _day(sim, d_iso)["entries"]
    assert [x["id"] for x in new] == [e["id"]]
    assert new[0]["note"] == "ny note"


def test_set_day_creates_missing_day():
    plan = _plan()
    sim, dates = proposals.apply_changes(plan, [{"date": "2027-12-24", "action": "set_day",
                                                 "entries": [_styrke()]}])
    assert _day(sim, "2027-12-24")["entries"][0]["templateId"] == "styrke-fs4-a-2r"
    ds = [d["date"] for d in sim["athletes"]["kennet"]["days"]]
    assert ds == sorted(ds)


# -- validate -------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    {"status": "maybe"},
    {"changes": [{"date": "2026-10-01", "action": "move", "entries": []}]},
    {"changes": [{"date": "1/10", "action": "set_day", "entries": []}]},
    {"changes": [{"date": "2026-10-01", "action": "set_day", "entries": []},
                 {"date": "2026-10-01", "action": "set_day", "entries": []}]},
    {"changes": [{"date": "2026-10-01", "action": "set_day", "entries": [{"workout": {"name": "x"}}]}]},
])
def test_validate_rejects(bad):
    p = _prop([])
    p.update(bad)
    with pytest.raises(ValueError):
        proposals.validate(p)


def test_pid_from_entry_id():
    assert proposals.pid_from_entry_id("proposal:2026-09-07-uge3-8") == "2026-09-07-uge3-8"
    for bad in ("2026-09-07-uge3-8", "proposal:", ""):
        with pytest.raises(ValueError):
            proposals.pid_from_entry_id(bad)


# -- gennem edit_apply (samme vej som live) --------------------------------------

def test_apply_proposal_via_edit_apply_ok():
    plan = _plan()
    d1, d2 = _future_free_dates(plan)
    prop = _prop([{"date": d1, "action": "set_day", "entries": [_styrke()]},
                  {"date": d2, "action": "set_day", "entries": []}])
    res = edit_apply.apply_edit(json.dumps(plan), "apply_proposal", "proposal:t-1", {"proposal": prop})
    assert res["status"] == "ok", res["gate"]
    assert res["dates_changed"] == [d1, d2]
    assert res["proposal_id"] == "t-1"
    new = json.loads(res["new_plan_raw"])
    assert _day(new, d1)["entries"][0]["templateId"] == "styrke-fs4-a-2r"
    assert _day(new, d2)["entries"] == []


def test_apply_proposal_rejects_on_check_week_violation():
    """Tre hårde kælderpas i én uge -> bike_library.check_week bryder -> reject."""
    plan = _plan()
    # sidste mandag i planen (26/10) — læg hårde pas man/ons/fre
    from datetime import date, timedelta
    mon = max(d["date"] for d in plan["athletes"]["kennet"]["days"]
              if date.fromisoformat(d["date"]).weekday() == 0)
    m = date.fromisoformat(mon)
    changes = []
    for off, wid in ((0, "tae_3x12"), (2, "tae_over_unders"), (4, "tae_3x12")):
        t = edit_apply._find_template(wid)
        changes.append({"date": (m + timedelta(days=off)).isoformat(), "action": "set_day",
                        "entries": [{"workout": {k: t[k] for k in ("name", "type", "moving_time", "description")},
                                     "libraryId": wid}]})
    # øvrige dage i ugen tømmes så kun de tre pas tæller
    for off in (1, 3, 5, 6):
        changes.append({"date": (m + timedelta(days=off)).isoformat(), "action": "set_day", "entries": []})
    res = edit_apply.apply_edit(json.dumps(plan), "apply_proposal", "proposal:t-1",
                                {"proposal": _prop(changes)}, confirmed_warn=True)
    assert res["status"] == "reject"
    assert "kælderregel" in res["gate"]["msg"]
    assert "hårde pas" in res["gate"]["msg"]
    assert "new_plan_raw" not in res


def test_apply_proposal_refuses_decided_and_mismatched():
    plan = _plan()
    d1, = _future_free_dates(plan, 1)
    prop = _prop([{"date": d1, "action": "set_day", "entries": []}], status="accepted")
    with pytest.raises(ValueError, match="allerede afgjort"):
        edit_apply.apply_edit(json.dumps(plan), "apply_proposal", "proposal:t-1", {"proposal": prop})
    prop["status"] = "pending"
    with pytest.raises(ValueError, match="matcher ikke"):
        edit_apply.apply_edit(json.dumps(plan), "apply_proposal", "proposal:andet", {"proposal": prop})


def test_reject_proposal_changes_nothing():
    plan = _plan()
    d1, = _future_free_dates(plan, 1)
    prop = _prop([{"date": d1, "action": "set_day", "entries": []}])
    res = edit_apply.apply_edit(json.dumps(plan), "reject_proposal", "proposal:t-1",
                                {"proposal": prop, "reason": "nej"})
    assert res["status"] == "ok" and res["dates_changed"] == [] and res["proposal_id"] == "t-1"
    assert json.loads(res["new_plan_raw"]) == plan


def test_apply_proposal_loads_file_from_dir(tmp_path):
    plan = _plan()
    d1, = _future_free_dates(plan, 1)
    prop = _prop([{"date": d1, "action": "set_day", "entries": [_styrke()]}], pid="fil-1")
    proposals.save(prop, tmp_path)
    assert proposals.load("fil-1", tmp_path)["id"] == "fil-1"
    assert [p["id"] for p in proposals.list_pending(tmp_path)] == ["fil-1"]
    with pytest.raises(ValueError, match="findes ikke"):
        proposals.load("nix", tmp_path)


# -- offline anvendelse = live-koden ------------------------------------------

def test_apply_offline_writes_plan_and_status(tmp_path):
    plan = _plan()
    d1, = _future_free_dates(plan, 1)
    prop = _prop([{"date": d1, "action": "set_day", "entries": [_styrke()]}], pid="off-1")
    proposals.save(prop, tmp_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    res = proposals.apply_offline("off-1", plan_path=plan_path, root=tmp_path)
    assert res["status"] == "ok"
    new = json.loads(plan_path.read_text(encoding="utf-8"))
    assert _day(new, d1)["entries"][0]["templateId"] == "styrke-fs4-a-2r"
    saved = proposals.load("off-1", tmp_path)
    assert saved["status"] == "applied-offline"
    assert saved["result"]["dates_changed"] == [d1] and saved["decidedAt"]
    # anden gang: allerede afgjort
    with pytest.raises(ValueError, match="allerede afgjort"):
        proposals.apply_offline("off-1", plan_path=plan_path, root=tmp_path)


# -- data.json-visning ----------------------------------------------------------

def test_summarize_for_data_before_after_per_week():
    plan = _plan()
    d1, d2 = _future_free_dates(plan)
    before1 = [e["workout"]["name"] for e in _day(plan, d1)["entries"] if e.get("workout")]
    prop = _prop([{"date": d1, "action": "set_day", "entries": [_styrke()]},
                  {"date": d2, "action": "set_day", "entries": []}])
    s = proposals.summarize_for_data(plan, prop)
    assert s["id"] == "t-1" and s["status"] == "pending" and s["summary"] == ["s"]
    days = {d["date"]: d for w in s["weeks"] for d in w["days"]}
    assert days[d1]["before"] == before1
    assert days[d1]["after"] == ["Styrke A · Functional 4 · 2 runder"]
    assert days[d2]["after"] == []
    for w in s["weeks"]:
        assert isinstance(w["isoWeek"], int) and w["start"] <= w["days"][0]["date"]


def test_build_data_proposals_only_pending(tmp_path):
    plan = _plan()
    d1, = _future_free_dates(plan, 1)
    proposals.save(_prop([{"date": d1, "action": "set_day", "entries": []}], pid="p-1"), tmp_path)
    proposals.save(_prop([{"date": d1, "action": "set_day", "entries": []}], pid="p-2",
                         status="rejected"), tmp_path)
    (tmp_path / "defekt.json").write_text("{", encoding="utf-8")
    out = proposals.build_data_proposals(plan, tmp_path)
    assert [p["id"] for p in out] == ["p-1"]
    assert proposals.build_data_proposals(plan, tmp_path / "findes-ikke") == []


def test_data_proposals_matches_data_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "schemas" / "data.schema.json").read_text(encoding="utf-8"))
    plan = _plan()
    d1, = _future_free_dates(plan, 1)
    proposals.save(_prop([{"date": d1, "action": "set_day", "entries": [_styrke()]}], pid="p-1"), tmp_path)
    out = proposals.build_data_proposals(plan, tmp_path)
    sub = {"type": "object", "properties": {"proposals": schema["properties"]["proposals"]}}
    assert not list(jsonschema.Draft202012Validator(sub).iter_errors({"proposals": out}))
    # og et brud fanges: status skal være pending
    out[0]["status"] = "accepted"
    assert list(jsonschema.Draft202012Validator(sub).iter_errors({"proposals": out}))


# -- de rigtige forslag (uge 3-8 fra blok 9; uge 39-53 fra blok 11) ----------
# Blok 11 (11/9-2026) overskrev uge 3-8 med TMB-rammen: lang tur søndag, svøm
# 1×/uge, VO2-blok uge 45-51. Forslaget fra blok 9 bevares som historik.
REAL_PROPOSAL_11 = ROOT / "data" / "proposals" / "2026-09-11-uge39-53.json"


def test_real_proposal_blok9_is_history():
    prop = json.loads(REAL_PROPOSAL.read_text(encoding="utf-8"))
    proposals.validate(prop)
    assert prop["status"] == "applied-offline"
    assert len(prop["changes"]) == 20


def test_real_proposal_blok11_applied_offline_and_plan_matches():
    prop = json.loads(REAL_PROPOSAL_11.read_text(encoding="utf-8"))
    proposals.validate(prop)
    assert prop["status"] == "applied-offline"
    assert len(prop["changes"]) == 105                     # 15 uger × 7 dage
    assert prop["changes"][0]["date"] == "2026-09-21"
    assert prop["changes"][-1]["date"] == "2027-01-03"
    by_week = {}
    for d in PLAN["athletes"]["kennet"]["days"]:
        if "2026-09-21" <= d["date"] <= "2027-01-03":
            wk = date.fromisoformat(d["date"]).isocalendar()[1]
            for e in d["entries"]:
                wo = e.get("workout") or {}
                by_week.setdefault(wk, []).append((d["date"], wo.get("type"), e.get("libraryId"), e.get("templateId")))
                if wo.get("type") == "WeightTraining":
                    assert e.get("templateId") in ("styrke-fs4-a-2r", "styrke-fs4-b-2r"), d["date"]
                if e.get("libraryId"):
                    assert e["libraryId"] in bike_library.ids(), d["date"]
    for wk, rows in by_week.items():
        assert sum(1 for r in rows if r[1] == "Swim") == 1, ("svøm 1×/uge", wk)
        assert sum(1 for r in rows if r[1] == "WeightTraining") == 2, ("styrke 2×/uge", wk)
        sundays = [r for r in rows if date.fromisoformat(r[0]).weekday() == 6]
        assert sundays and sundays[0][1] == "Ride", ("lang tur søndag", wk)
    # kælderreglen holder i alle 15 uger
    assert proposals.check_weeks(PLAN, [c["date"] for c in prop["changes"]]) == []


def test_real_proposal_blok11_quotas():
    quota = {"2026-09-21": (1, 0), "2026-09-28": (0, 0), "2026-10-05": (0, 0), "2026-10-12": (0, 2),
             "2026-10-19": (2, 0), "2026-10-26": (0, 0), "2026-11-02": (1, 0), "2026-11-09": (1, 2),
             "2026-11-16": (1, 0), "2026-11-23": (0, 0), "2026-11-30": (2, 0), "2026-12-07": (1, 1),
             "2026-12-14": (1, 1), "2026-12-21": (0, 0), "2026-12-28": (1, 0)}
    for start, (h, m) in quota.items():
        c = proposals.week_load_counts(PLAN, "kennet", start)
        assert (c["haard"], c["moderat"]) == (h, m), (start, c)
