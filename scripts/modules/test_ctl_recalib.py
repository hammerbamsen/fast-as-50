# -*- coding: utf-8 -*-
"""CTL-rekalibrering ved porte (14/9-2026)."""
import copy
import json
from datetime import date
from pathlib import Path

from . import ctl_recalib as cr, proposals as pr, programs as _programs

PLAN = json.loads((Path(__file__).resolve().parent.parent.parent / "data" / "plan.json").read_text(encoding="utf-8"))

# Målene i plan.json flyttes af accepterede ctl-recalib-forslag (første gang 14/9-2026).
# Testene her regner på de OPRINDELIGE tds-2027-mål for uge 2-9, så de ikke knækker
# hver gang en port accepteres.
_ORIG_TARGETS = {2: (45, 250), 3: (48, 380), 4: (51, 480), 5: (50, 250),
                 6: (53, 420), 7: (56, 440), 8: (55, 260), 9: (57, 440)}


def _plan_before_recalib(plan: dict) -> dict:
    p = copy.deepcopy(plan)
    for w in p["programs"]["tds-2027"]["weeks"]:
        if w.get("week") in _ORIG_TARGETS:
            w["ctlTarget"], w["tssTarget"] = _ORIG_TARGETS[w["week"]]
    return p


PLAN0 = _plan_before_recalib(PLAN)


def test_offsets_decay():
    assert cr.offsets(5, 8) == [5, 4, 4, 3, 2, 2, 1, 1]
    assert cr.offsets(3, 8)[0] == 3 and cr.offsets(3, 8)[-1] == 0


def test_port_detection():
    prog = _programs.active_program(PLAN, "kennet", date(2026, 9, 14))
    assert cr._is_port(prog, date(2026, 9, 14))[0]          # mandag efter RECOVERY uge 1
    assert not cr._is_port(prog, date(2026, 9, 15))[0]      # tirsdag
    assert not cr._is_port(prog, date(2026, 9, 21))[0]      # mandag efter RACE-uge
    assert cr._is_port(prog, date(2026, 9, 28))[0]          # mandag efter uge 3 (FTP-test 24/9)


def test_no_proposal_below_threshold_or_downward():
    assert cr.build_proposal(PLAN0, 46.0, date(2026, 9, 14), "t") is None     # +1 < 3
    r = cr.build_proposal(PLAN0, 40.0, date(2026, 9, 14), "t")
    assert r and "warning" in r and "changes" not in r                       # nedad = kun advarsel


def test_proposal_shape_and_protection():
    p = cr.build_proposal(PLAN0, 50.3, date(2026, 9, 14), "t")
    pr.validate(p)
    assert p["status"] == "pending" and p["id"] == "ctl-recalib-2026-09-14"
    weeks = {c["week"]: c for c in p["changes"]}
    assert weeks[2] == {"action": "set_week_targets", "programId": "tds-2027", "week": 2, "ctlTarget": 50}
    assert weeks[3]["ctlTarget"] == 53 and weeks[3]["tssTarget"] == 380 + 5 * cr.TSS_PER_CTL
    assert max(weeks) < 11                                                   # uge 11 (BASE+ 62) urørt
    sim, dates = pr.apply_changes(PLAN0, p["changes"])
    assert dates == []
    assert _programs.week_meta(_programs.active_program(sim, "kennet", date(2026, 9, 14)), 3)["ctlTarget"] == 53
    assert _programs.week_meta(_programs.active_program(PLAN0, "kennet", date(2026, 9, 14)), 3)["ctlTarget"] == 48
    t = pr.target_changes_for_data(PLAN0, p["changes"])
    assert t[0]["isoWeek"] == 38 and t[1]["ctlBefore"] == 48 and t[1]["ctlAfter"] == 53


def test_future_race_week_protected():
    # Uge 39 i tds-2027 (Stelvio, RACE) må aldrig forskydes: byg fra en mandag lige før.
    prog = _programs.active_program(PLAN, "kennet", date(2027, 5, 24))
    p = cr.build_proposal(PLAN, prog["weeks"][37]["ctlTarget"] + 6, date(2027, 5, 24), "t")
    assert p and all(c["week"] != 39 for c in p["changes"][1:])


def test_recent_guard(tmp_path):
    pr.save({"id": "ctl-recalib-2026-09-10", "title": "x", "status": "rejected", "changes": []}, tmp_path)
    assert cr.recent_recalib_exists(tmp_path, today=date(2026, 9, 14))
    assert not cr.recent_recalib_exists(tmp_path, today=date(2026, 10, 14))
    assert cr.maybe_propose(PLAN, 50.3, date(2026, 9, 14), force=True, root=tmp_path) is None
    assert cr.maybe_propose(PLAN, 60.0, date(2026, 10, 14), force=True, root=tmp_path)


def test_validate_rejects_bad_targets():
    import pytest
    bad = {"id": "x", "title": "x", "status": "pending",
           "changes": [{"action": "set_week_targets", "programId": "tds-2027", "week": 3}]}
    with pytest.raises(ValueError):
        pr.validate(bad)
