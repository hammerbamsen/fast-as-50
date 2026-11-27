# -*- coding: utf-8 -*-
"""Tests for vo2_dose (27/11-2026).

Kør: python3 -m pytest scripts/modules/test_vo2_dose.py -q
"""
import json
from datetime import date, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import vo2_dose

ROOT = Path(__file__).resolve().parent.parent.parent
PLAN = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))


def _ride(day, z5_secs, z1_secs=3600):
    """Cykelpas med power-zonetider (icu_zone_times = liste af {id, secs})."""
    return {"type": "Ride", "start_date_local": f"{day}T08:00:00",
            "icu_zone_times": [{"id": f"Z{i + 1}", "secs": s} for i, s in
                               enumerate([z1_secs, 0, 0, 0, z5_secs, 0, 0])]}


def _run(day, z5_secs, z1_secs=1800):
    """Løbepas med HR-zonetider (icu_hr_zone_times = flad liste)."""
    return {"type": "Run", "start_date_local": f"{day}T08:00:00",
            "icu_hr_zone_times": [z1_secs, 0, 0, 0, z5_secs, 0, 0]}


def test_cykel_maales_paa_watt_og_loeb_paa_puls():
    assert vo2_dose._z5_secs(_ride("2027-03-16", 600)) == 600
    assert vo2_dose._z5_secs(_run("2027-03-16", 300)) == 300
    # cykelpas uden power-zoner falder tilbage paa puls
    r = _run("2027-03-16", 420); r["type"] = "Ride"
    assert vo2_dose._z5_secs(r) == 420
    assert vo2_dose._z5_secs({"type": "Ride", "start_date_local": "2027-03-16T08:00"}) == 0


def test_weekly_bucketer_paa_kalenderuge_og_taeller_kun_rigtige_pas():
    today = date(2027, 3, 18)              # torsdag i KU11
    monday = date(2027, 3, 15)
    acts = [
        _ride(monday.isoformat(), 600),                       # 10 min -> tael
        _ride((monday + timedelta(days=2)).isoformat(), 120),  # 2 min -> for lille
        _run((monday - timedelta(days=7)).isoformat(), 300),   # ugen foer
        _ride("2026-12-01", 900),                              # uden for vinduet
    ]
    rows = vo2_dose.weekly(acts, PLAN, today=today, weeks=4)
    assert [r["isoWeek"] for r in rows] == [8, 9, 10, 11]
    assert rows[-1]["z5Min"] == 12 and rows[-1]["sessions"] == 1
    assert rows[-2]["z5Min"] == 5 and rows[-2]["sessions"] == 1


def test_maaldosis_foelger_fasen_og_nulstilles_i_restitutionsuger():
    """Laaser ikke en bestemt uges blockType — den kan aendres via forslag.
    Tjekker i stedet reglen: fasen giver maalet, og BLOCK_ZERO nulstiller det."""
    prog = PLAN["programs"]["tds-2027"]
    for w in prog["weeks"]:
        t, phase, bt = vo2_dose.week_target(PLAN, date.fromisoformat(w["start"]))
        assert bt == w["blockType"]
        assert phase == w.get("phase")          # fasen, aldrig blocktypen
        up = str(w["blockType"]).upper()
        if up.startswith(vo2_dose.BLOCK_ZERO) or up == "RACE":
            assert t == 0, f"uge {w['week']} ({up}) burde have maal 0"
        elif phase == "BASE":
            assert 5 <= t <= 15
        elif phase in vo2_dose.PHASE_TARGET:
            assert t == vo2_dose.PHASE_TARGET[phase]
    # blockType som argument slaar planen
    assert vo2_dose.week_target(PLAN, date(2027, 3, 15), block_type="RECOVERY")[0] == 0
    # uge uden for programmet
    assert vo2_dose.week_target(PLAN, date(2030, 1, 7))[0] is None


def test_base_ramper_fra_5_til_15_minutter():
    phases = (PLAN.get("season2027") or {}).get("phases") or []
    base = next(p for p in phases if p["name"] == "BASE")
    prog = PLAN["programs"]["tds-2027"]
    uger = [w for w in prog["weeks"]
            if base["weekFrom"] <= w["week"] <= base["weekTo"]
            and not str(w["blockType"]).upper().startswith(("RECOVERY", "REST", "TAPER"))
            and w["blockType"] != "RACE"]
    maal = [vo2_dose.week_target(PLAN, date.fromisoformat(w["start"]))[0] for w in uger]
    assert min(maal) >= 5 and max(maal) <= 15
    assert maal == sorted(maal)             # monotont stigende gennem basen


def test_card_farver():
    today = date(2027, 3, 18)              # torsdag i KU11, maal 15 min
    monday = date(2027, 3, 15)
    paa_maal = vo2_dose.card([_ride(monday.isoformat(), 840)], PLAN, today=today)
    assert paa_maal["color"] == "#27AE60" and paa_maal["z5Min"] == 14
    # ugen er ikke omme -> lav dosis doemmes ikke endnu
    i_gang = vo2_dose.card([_ride(monday.isoformat(), 300)], PLAN, today=today)
    assert i_gang["color"] == "#7F8C8D" and "i gang" in i_gang["status"]
    assert i_gang["weekLate"] is False
    # samme dosis, men nu er det loerdag -> gul
    lordag = vo2_dose.card([_ride(monday.isoformat(), 300)], PLAN, today=date(2027, 3, 20))
    assert lordag["color"] == "#F39C12" and lordag["status"] == "under måldosis"
    for_meget = vo2_dose.card([_ride(monday.isoformat(), 1800)], PLAN, today=today)
    assert for_meget["color"] == "#C0392B" and "maks" in for_meget["status"]
    tom = vo2_dose.card([], PLAN, today=date(2030, 1, 7))
    assert tom["color"] == "#7F8C8D" and tom["target"] is None


def test_tidligere_uger_vises_med_deres_eget_maal():
    acts = [_ride("2027-03-09", 300)]
    c = vo2_dose.card(acts, PLAN, today=date(2027, 3, 15), weeks=2)
    assert c["weeks"][0]["z5Min"] == 5 and c["weeks"][0]["isoWeek"] == 10
    assert c["weeks"][0]["target"] and c["weeks"][-1]["z5Min"] == 0


def test_card_restitutionsuge_straffer_z5():
    today = date(2027, 3, 25)              # KU12, RECOVERY -> maal 0
    ren = vo2_dose.card([], PLAN, today=today)
    assert ren["color"] == "#27AE60" and ren["target"] == 0
    snyd = vo2_dose.card([_ride("2027-03-23", 600)], PLAN, today=today)
    assert snyd["color"] == "#F39C12" and "kørt Z5" in snyd["status"]


def test_tre_uger_under_halv_dosis_giver_roedt():
    # KU20 (17-23/5). De tre foregaaende uger er omme og tomme; KU19 er CAMP,
    # KU18 BUILD, KU17 RECOVERY (maal 0, taeller ikke) -> vi skal laengere tilbage.
    c = vo2_dose.card([], PLAN, today=date(2027, 5, 20), weeks=6)
    afsluttede = [r for r in c["weeks"][:-1] if r["target"]]
    assert len(afsluttede) >= 3
    assert c["color"] == "#C0392B" and "halv dosis" in c["status"]


def test_restitutionsuger_taeller_ikke_i_streak():
    # Tre tomme uger hvoraf to er RECOVERY (maal 0) maa ikke give roedt
    c = vo2_dose.card([], PLAN, today=date(2027, 4, 29), weeks=3)
    maal_uger = [r for r in c["weeks"] if r["target"]]
    assert any(r["target"] == 0 for r in c["weeks"])
    assert c["color"] != "#C0392B" or len(maal_uger) > 3
