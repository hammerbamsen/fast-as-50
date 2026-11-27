# -*- coding: utf-8 -*-
"""Tests for week_brief — soendagsbriefen (27/11-2026)."""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import week_brief as wb


def _plan(days, blocktype="BASE", purpose="Build hjemme.", tss=460, travel=None):
    return {
        "programs": {"p": {"id": "p", "start": "2026-11-30", "end": "2027-01-10",
                           "athletes": ["kennet"], "totalWeeks": 6, "weeks": [
            {"week": w, "start": (date(2026, 11, 30) + __import__("datetime").timedelta(weeks=w - 1)).isoformat(),
             "blockType": blocktype, "phase": "BASE", "ctlTarget": 50, "tssTarget": tss,
             "purpose": purpose} for w in range(1, 7)]}},
        "travel": travel or [],
        "athletes": {"kennet": {"days": days}},
    }


def _day(d, *entries):
    return {"date": d, "entries": list(entries)}


def _wo(navn, type_="Ride", lib=None):
    e = {"id": navn[:6], "workout": {"type": type_, "name": navn}}
    if lib:
        e["libraryId"] = lib
    return e


def _uge(start, n=7):
    """En fuldt planlagt uge: Z2 mandag, haardt pas tirsdag, resten let."""
    from datetime import timedelta
    d0 = date.fromisoformat(start)
    ud = [_day((d0 + timedelta(days=0)).isoformat(), _wo("FaF 1 Z2 - Rolig 60", lib="z2_rolig_60")),
          _day((d0 + timedelta(days=1)).isoformat(), _wo("FaF 4 Tær - 2 x 20", lib="tae_2x20")),
          _day((d0 + timedelta(days=2)).isoformat(), _wo("Løb Z2 45 min", "Run")),
          _day((d0 + timedelta(days=3)).isoformat(), _wo("Styrke A", "WeightTraining"))]
    return ud[:n]


def test_next_monday_fra_soendag_er_i_morgen():
    assert wb.next_monday("2026-11-29") == date(2026, 11, 30)
    assert wb.next_monday("2026-11-30") == date(2026, 12, 7)   # mandag -> naeste mandag
    assert wb.next_monday(date(2026, 12, 2)) == date(2026, 12, 7)


def test_brief_paa_en_planlagt_uge():
    plan = _plan(_uge("2026-11-30"))
    m = wb.build(plan, "kennet", today="2026-11-29")
    assert m["title"] == "KU49 · BASE · 460 TSS"
    assert m["body"].startswith("4 pas: ")
    assert "cykel" in m["body"] and "løb" in m["body"] and "styrke" in m["body"]
    assert "Hårdt: FaF 4 Tær - 2 x 20." in m["body"]
    assert m["tag"] == "fast50-week" and m["athlete"] == "kennet"
    assert m["dage"] == 4


def test_brief_siger_til_naar_ugen_slet_ikke_er_lagt():
    """Den hyppigste aarsag til en improviseret uge: ingen dage i planen."""
    plan = _plan([], purpose="Build hjemme. Søndag 5 t.")
    m = wb.build(plan, "kennet", today="2026-11-29")
    assert m["title"] == "KU49 er ikke lagt endnu"
    assert "460 TSS" in m["body"] and "Søndag 5 t" in m["body"]
    assert m["dage"] == 0


def test_brief_naevner_hvad_der_skal_rettes():
    # tre haarde pas i samme uge -> hard_per_week + hard_spacing
    d0 = "2026-11-30"
    days = [_day("2026-11-30", _wo("FaF 4 Tær - 2 x 20", lib="tae_2x20")),
            _day("2026-12-01", _wo("FaF 5 VO2 - 4 x 4", lib="vo2_4x4")),
            _day("2026-12-02", _wo("FaF 4 Tær - 3 x 12", lib="tae_3x12")),
            _day("2026-12-03", _wo("Styrke A", "WeightTraining"))]
    m = wb.build(_plan(days, blocktype="BUILD"), "kennet", today="2026-11-29")
    assert "at rette" in m["body"]
    regler = {f["rule"] for f in m["flags"]}
    assert "hard_per_week" in regler
    assert any("hårde" in f["kort"] for f in m["flags"])


def test_brief_siger_intet_at_rette_naar_ugen_er_ren():
    m = wb.build(_plan(_uge("2026-11-30")), "kennet", today="2026-11-29")
    assert "Intet at rette." in m["body"] and m["flags"] == []


def test_ingen_brief_uden_for_programmet():
    plan = _plan(_uge("2026-11-30"))
    assert wb.build(plan, "kennet", today="2030-01-06") is None


def test_body_er_kort_nok_til_en_laasskaerm():
    plan = _plan(_uge("2026-11-30"), purpose="x" * 500)
    m = wb.build(plan, "kennet", today="2026-11-29")
    assert len(m["body"]) <= 220
    tom = wb.build(_plan([], purpose="y" * 500), "kennet", today="2026-11-29")
    assert len(tom["body"]) <= 220


def test_week_plan_mod_den_rigtige_plan():
    """Kontrakten mod den rigtige plan.json — uden at laase en bestemt uges indhold."""
    import json
    plan = json.loads((Path(__file__).resolve().parent.parent.parent / "data" / "plan.json")
                      .read_text(encoding="utf-8"))
    m = wb.build(plan, "kennet", today="2026-11-29")
    assert m is not None
    assert m["title"].startswith("KU")
    assert m["tag"] == "fast50-week" and len(m["body"]) <= 220
