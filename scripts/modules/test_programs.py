# -*- coding: utf-8 -*-
"""Tests for programs.py — programvalg efter dato, uge/dag-beregning, legacy-syntese."""
import json
from datetime import date, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import programs as P

PLAN = json.loads(
    (Path(__file__).resolve().parent.parent.parent / "data" / "plan.json")
    .read_text(encoding="utf-8"))


# ── Rigtig plan.json ────────────────────────────────────────────────────────

def test_real_plan_has_programs_with_required_fields():
    progs = P.list_programs(PLAN)
    assert {"medoc-2026", "tds-2027"} <= set(progs)
    for pid, p in progs.items():
        for k in ("id", "name", "athletes", "start", "end", "totalWeeks", "weeks", "races"):
            assert k in p, (pid, k)
        assert p["id"] == pid
        assert len(p["weeks"]) == p["totalWeeks"], pid
        # start + totalWeeks*7 - 1 == end
        assert (date.fromisoformat(p["start"]) + timedelta(days=p["totalWeeks"] * 7 - 1)
                == date.fromisoformat(p["end"])), pid


def test_real_plan_programs_are_contiguous_for_kennet():
    ps = P.programs_for(PLAN, "kennet")
    ps = [p for p in ps if not p.get("_athleteLevel")]
    for a, b in zip(ps, ps[1:]):
        assert date.fromisoformat(a["end"]) + timedelta(days=1) == date.fromisoformat(b["start"]), \
            (a["id"], b["id"])


def test_active_program_every_day_2026_06_01_to_2027_08_29():
    d = date(2026, 6, 1)
    while d <= date(2027, 8, 29):
        p = P.active_program(PLAN, "kennet", d)
        assert p is not None, d
        assert P.in_program(p, d), (d, p["id"])
        d += timedelta(days=1)


def test_every_planned_day_has_a_week_with_ctl_target():
    """Hver dato i athletes.kennet.days ligger i et program hvis uge har ctlTarget."""
    for day in PLAN["athletes"]["kennet"]["days"]:
        d = date.fromisoformat(day["date"])
        p = P.active_program(PLAN, "kennet", d)
        assert P.in_program(p, d), (day["date"], p["id"])
        w = P.week_no(p, d)
        assert P.week_meta(p, w).get("ctlTarget") is not None, (day["date"], p["id"], w)


def test_expected_week_lookup_on_key_dates():
    exp = {
        "2026-09-03": ("medoc-2026", 14, "RACE"),
        "2026-09-06": ("medoc-2026", 14, "RACE"),
        "2026-09-07": ("tds-2027", 1, "RECOVERY"),
        "2026-09-20": ("tds-2027", 2, "RACE"),
        "2026-09-21": ("tds-2027", 3, "BASE"),
        "2026-10-09": ("tds-2027", 5, "RECOVERY"),
        "2027-08-28": ("tds-2027", 51, "RACE"),
    }
    for d, (pid, w, bt) in exp.items():
        p = P.active_program(PLAN, "kennet", d)
        assert p["id"] == pid, d
        assert P.week_no(p, d) == w, d
        assert P.week_meta(p, w)["blockType"] == bt, d


def test_after_last_program_freezes_on_latest_started():
    p = P.active_program(PLAN, "kennet", "2027-12-24")
    assert p["id"] == "tds-2027"
    assert P.week_no(p, "2027-12-24") == 51


def test_before_first_program_returns_first_upcoming():
    p = P.active_program(PLAN, "kennet", "2026-01-01")
    assert p["id"] == "medoc-2026"
    assert P.week_no(p, "2026-01-01") == 1


def test_tds_weeks_1_2_match_legacy_15_16():
    tds = P.list_programs(PLAN)["tds-2027"]
    w1, w2 = P.week_meta(tds, 1), P.week_meta(tds, 2)
    assert (w1["blockType"], w1["ctlTarget"], w1["tssTarget"]) == ("RECOVERY", 47, 150)
    # ctlTarget for uge 2+ kan være løftet af et accepteret ctl-recalib-forslag
    # (første gang 14/9-2026: 45 → 50) — test kun bloktype, TSS og at målet
    # ikke er under det oprindelige.
    assert (w2["blockType"], w2["tssTarget"]) == ("RACE", 250)
    assert w2["ctlTarget"] >= 45
    # legacy uge 15-16 (plan.json.weeks) er frosset på de oprindelige tal
    legacy = {w["week"]: w for w in PLAN["weeks"]}
    assert legacy[15]["ctlTarget"] == 47 and legacy[16]["ctlTarget"] == 45
    # season2027.weeks er en frosset kopi; ctl/tss-mål i programmet kan være rekalibreret
    strip = lambda ws: [{k: v for k, v in w.items() if k not in ("ctlTarget", "tssTarget")} for w in ws]
    assert strip(PLAN["season2027"]["weeks"][:8]) == strip(tds["weeks"][:8])
    for w in tds["weeks"][:8]:
        assert "purpose" in w and set(w["quota"]) == {"haard", "moderat"}
    assert w1["phase"] == "TRANSITION" and w1["ftpTarget"] == 278
    assert tds["weightPlan"]["cutStartsFrom"] == "2026-09-21"
    assert "21/9" in tds["weightPlan"]["note"] and "19 uger" in tds["weightPlan"]["note"]


def test_next_race_and_upcoming_across_programs():
    medoc = P.list_programs(PLAN)["medoc-2026"]
    r = P.next_race(medoc, "2026-09-03")
    assert r["name"] == "Marathon du Médoc" and r["daysTo"] == 2
    assert P.next_race(medoc, "2026-09-06") is None
    up = P.upcoming_races(PLAN, "kennet", "2026-09-06")
    assert up[0]["name"] == "CPH Half" and up[0]["daysTo"] == 14
    assert [r["name"] for r in up][-1] == "Tour des Stations Ultrafondo"
    # Ingen dubletter
    assert len({(r["name"], r["date"]) for r in up}) == len(up)


def test_eva_gets_her_own_program():
    p = P.active_program(PLAN, "eva", "2026-09-03")
    assert p.get("_athleteLevel") and p["athletes"] == ["eva"]
    assert p["start"] == PLAN["athletes"]["eva"]["program"]["start"]
    assert p["totalWeeks"] == PLAN["athletes"]["eva"]["program"]["totalWeeks"]
    assert p["weeks"] == PLAN["athletes"]["eva"]["weeks"]
    # Frosset efter programslut — aldrig None
    assert P.active_program(PLAN, "eva", "2026-12-01")["id"] == p["id"]


def test_ctl_plan_and_block_types():
    tds = P.list_programs(PLAN)["tds-2027"]
    cp = P.ctl_plan(tds)
    assert len(cp) == 51 and cp[0] == 47 and cp[-1] == 82
    bt = P.block_types(tds)
    assert bt[1] == "RECOVERY" and bt[51] == "RACE"


def test_program_day_and_days_total():
    medoc = P.list_programs(PLAN)["medoc-2026"]
    assert P.days_total(medoc) == 98
    assert P.program_day(medoc, "2026-06-01") == 1
    assert P.program_day(medoc, "2026-09-06") == 98
    assert P.program_day(medoc, "2026-09-30") == 98   # clamp


def test_actuals_through_week_is_program_scoped():
    progs = P.list_programs(PLAN)
    assert P.actuals_through_week(PLAN, "kennet", progs["medoc-2026"]) == \
        PLAN["athletes"]["kennet"]["actualsThroughWeek"]
    assert P.actuals_through_week(PLAN, "kennet", progs["tds-2027"]) == 0


# ── Legacy-fixtures (som friel-/adaptation-tests bruger) ────────────────────

def _legacy(total_weeks=2, start="2026-06-01"):
    return {
        "program": {"start": start, "totalWeeks": total_weeks},
        "weeks": [{"week": w, "blockType": "BUILD", "tssTarget": 300, "ctlTarget": 30 + w}
                  for w in range(1, total_weeks + 1)],
        "athletes": {"kennet": {"days": []}},
    }


def test_legacy_synthesis():
    plan = _legacy()
    progs = P.list_programs(plan)
    assert len(progs) == 1
    p = next(iter(progs.values()))
    assert p["start"] == "2026-06-01" and p["end"] == "2026-06-14" and p["totalWeeks"] == 2
    assert P.ctl_plan(p) == [31, 32]
    # Uanset dato: ét program -> altid det
    for d in ("2025-01-01", "2026-06-05", "2030-01-01"):
        assert P.active_program(plan, "kennet", d) is p or \
            P.active_program(plan, "kennet", d)["id"] == p["id"]


def test_legacy_with_season2027_synthesizes_second_program():
    plan = _legacy(total_weeks=14)
    plan["season2027"] = {"targetRace": "x-2027",
                          "weeks": [{"week": w, "start": (date(2026, 9, 7) + timedelta(weeks=w - 1)).isoformat(),
                                     "blockType": "BASE", "ctlTarget": 50, "tssTarget": 300}
                                    for w in range(1, 4)]}
    progs = P.list_programs(plan)
    assert set(progs) == {"legacy", "x-2027"}
    assert P.active_program(plan, "kennet", "2026-09-08")["id"] == "x-2027"
    assert P.active_program(plan, "kennet", "2026-07-01")["id"] == "legacy"


def test_no_programs_at_all_returns_none():
    assert P.active_program({}, "kennet", "2026-09-01") is None
    assert P.list_programs({}) == {}
