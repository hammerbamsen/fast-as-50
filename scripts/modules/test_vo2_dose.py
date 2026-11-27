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

# QA 27/11-2026 (fund 11): farve- og statustests laaste uge 28's og 29's
# blockType i den RIGTIGE plan.json — netop det et set_week_targets-forslag nu
# kan aendre. De bruger derfor denne faste fixture-plan i stedet. Kun
# fasereglen testes mod den rigtige plan, og da uden at laase en bestemt uge.
FIX = {
    "programs": {"tds-2027": {"start": "2026-09-07", "end": "2027-08-29",
                              "totalWeeks": 4, "weeks": [
        {"week": 1, "start": "2027-03-01", "phase": "BUILD", "blockType": "BUILD"},
        {"week": 2, "start": "2027-03-08", "phase": "BUILD", "blockType": "BUILD"},
        {"week": 3, "start": "2027-03-15", "phase": "BUILD", "blockType": "CAMP"},
        {"week": 4, "start": "2027-03-22", "phase": "BUILD", "blockType": "RECOVERY"},
    ]}},
    "season2027": {"phases": [{"name": "BUILD", "weekFrom": 1, "weekTo": 4}]},
}


def _ride(day, z5_secs, z1_secs=3600, z4_secs=600, z6_secs=0, z7_secs=0, wtype="Ride"):
    """Cykelpas med power-zonetider (icu_zone_times = liste af {id, secs}).

    Z4 er med som standard, saa en forskydning af zone-indekset (Z5 -> Z4)
    bliver fanget — det var hullet QA fandt 27/11-2026 (fund 8).
    """
    return {"type": wtype, "start_date_local": f"{day}T08:00:00",
            "icu_zone_times": [{"id": f"Z{i + 1}", "secs": s} for i, s in
                               enumerate([z1_secs, 0, 0, z4_secs, z5_secs, z6_secs, z7_secs])]}


def _run(day, z5_secs, z1_secs=1800, z4_secs=300):
    """Løbepas med HR-zonetider (icu_hr_zone_times = flad liste)."""
    return {"type": "Run", "start_date_local": f"{day}T08:00:00",
            "icu_hr_zone_times": [z1_secs, 0, 0, z4_secs, z5_secs, 0, 0]}


def test_zone_indeks_er_z5_og_kun_z5_for_watt():
    """Vigtigste egenskab i modulet: det er Z5 der taelles, ikke Z4 og ikke Z6/Z7."""
    assert vo2_dose._z5_secs(_ride("2027-03-16", 900, z4_secs=1200)) == 900   # Z4 ikke med
    assert vo2_dose._z5_secs(_ride("2027-03-16", 0, z4_secs=1200)) == 0
    # Z6/Z7 er anaerobt/neuromuskulaert, ikke VO2max-arbejde
    assert vo2_dose._z5_secs(_ride("2027-03-16", 0, z6_secs=300, z7_secs=180)) == 0
    assert vo2_dose._z5_secs(_ride("2027-03-16", 240, z6_secs=300)) == 240
    # puls: Z4 taeller ikke, Z5 og op gor
    assert vo2_dose._z5_secs(_run("2027-03-16", 300, z4_secs=900)) == 300


def test_alle_cykeltyper_maales_paa_watt():
    """Fund 4: Gravel og MountainBike faldt tilbage paa puls, saa dosis blev
    underrapporteret. Listen skal matche sessions.py."""
    for t in ("Ride", "VirtualRide", "MountainBike", "Cyclocross", "Gravel", "GravelRide"):
        a = _ride("2027-03-16", 900, wtype=t)
        a["icu_hr_zone_times"] = [1800, 0, 0, 0, 60, 0, 0]
        assert vo2_dose._z5_secs(a) == 900, f"{t} blev maalt paa puls"


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
    # Rampen skal faktisk rampe (fund 9: testen bestod ogsaa med BASE_RAMP=(15,15)).
    # Endepunkterne laases ikke mod den rigtige plan: sidste base-uge kan vaere en
    # RECOVERY- eller RACE-uge, saa den sidste MAALTE uge behoever ikke ligge paa 15.
    assert maal[0] == vo2_dose.BASE_RAMP[0]
    assert maal[-1] > maal[0]


def test_base_rampen_rammer_begge_endepunkter():
    """Praecis rampe 5 -> 15 paa en fixture hvor foerste og sidste base-uge er kendt."""
    fix = {
        "programs": {"tds-2027": {"start": "2026-09-07", "totalWeeks": 3, "weeks": [
            {"week": 1, "start": "2027-01-04", "phase": "BASE", "blockType": "BASE"},
            {"week": 2, "start": "2027-01-11", "phase": "BASE", "blockType": "BASE"},
            {"week": 3, "start": "2027-01-18", "phase": "BASE", "blockType": "BASE"},
        ]}},
        "season2027": {"phases": [{"name": "BASE", "weekFrom": 1, "weekTo": 3}]},
    }
    maal = [vo2_dose.week_target(fix, date(2027, 1, d))[0] for d in (4, 11, 18)]
    assert maal == [vo2_dose.BASE_RAMP[0], 10, vo2_dose.BASE_RAMP[1]]


def test_card_farver():
    today = date(2027, 3, 18)              # torsdag i fixture-ugen, maal 15 min
    monday = date(2027, 3, 15)
    paa_maal = vo2_dose.card([_ride(monday.isoformat(), 840)], FIX, today=today)
    assert paa_maal["color"] == "#27AE60" and paa_maal["z5Min"] == 14
    # ugen er ikke omme -> lav dosis doemmes ikke endnu
    i_gang = vo2_dose.card([_ride(monday.isoformat(), 300)], FIX, today=today)
    assert i_gang["color"] == "#7F8C8D" and "i gang" in i_gang["status"]
    assert i_gang["weekLate"] is False
    # samme dosis, men nu er det loerdag -> gul
    lordag = vo2_dose.card([_ride(monday.isoformat(), 300)], FIX, today=date(2027, 3, 20))
    assert lordag["color"] == "#F39C12" and lordag["status"] == "under måldosis"
    for_meget = vo2_dose.card([_ride(monday.isoformat(), 1800)], FIX, today=today)
    assert for_meget["color"] == "#C0392B" and "maks" in for_meget["status"]
    tom = vo2_dose.card([], FIX, today=date(2030, 1, 7))
    assert tom["color"] == "#7F8C8D" and tom["target"] is None and tom["status"] == "ingen data"


def test_tidligere_uger_vises_med_deres_eget_maal():
    acts = [_ride("2027-03-09", 300)]
    c = vo2_dose.card(acts, PLAN, today=date(2027, 3, 15), weeks=2)
    assert c["weeks"][0]["z5Min"] == 5 and c["weeks"][0]["isoWeek"] == 10
    assert c["weeks"][0]["target"] and c["weeks"][-1]["z5Min"] == 0


def test_card_restitutionsuge_straffer_z5():
    today = date(2027, 3, 25)              # fixture-uge 4, RECOVERY -> maal 0
    ren = vo2_dose.card([], FIX, today=today)
    assert ren["color"] == "#27AE60" and ren["target"] == 0
    snyd = vo2_dose.card([_ride("2027-03-23", 600)], FIX, today=today)
    assert snyd["color"] == "#F39C12" and "kørt Z5" in snyd["status"]


def test_uden_for_programmet_med_data_er_ikke_ingen_data():
    """Fund 6: 20 minutter ved siden af teksten "ingen data" er selvmodsigende."""
    c = vo2_dose.card([_ride("2030-01-08", 1200)], FIX, today=date(2030, 1, 10))
    assert c["z5Min"] == 20 and c["target"] is None
    assert "uden for programmet" in c["status"]
    assert vo2_dose.kpi(c)["sub"] == "uden for programmet"


def test_tre_uger_under_halv_dosis_giver_roedt():
    """Fixture-uge 1-3 er BUILD (maal 15) og tomme; uge 4 er den indevaerende.
    Uge 4 gores til BUILD, saa den har et reelt maal — ellers vinder maal-0-grenen."""
    fix = json.loads(json.dumps(FIX))
    fix["programs"]["tds-2027"]["weeks"][3]["blockType"] = "BUILD"
    c = vo2_dose.card([_ride("2027-03-23", 780)], fix, today=date(2027, 3, 25), weeks=4)
    afsluttede = [r for r in c["weeks"][:-1] if r["target"]]
    assert len(afsluttede) == 3 and all(r["z5Min"] == 0 for r in afsluttede)
    assert c["color"] == "#C0392B" and "halv dosis" in c["status"]


def test_restitutionsuger_taeller_ikke_i_streak():
    """Fund 9: med en RECOVERY-uge (maal 0) blandt de tre afsluttede er der kun
    to uger med reelt maal, og streak-reglen maa derfor ikke udloese roedt."""
    fix = json.loads(json.dumps(FIX))
    fix["programs"]["tds-2027"]["weeks"][3]["blockType"] = "BUILD"
    fix["programs"]["tds-2027"]["weeks"][1]["blockType"] = "RECOVERY"
    c = vo2_dose.card([_ride("2027-03-23", 780)], fix, today=date(2027, 3, 25), weeks=4)
    afsluttede = [r for r in c["weeks"][:-1] if r["target"]]
    assert len(afsluttede) == 2            # RECOVERY-ugen taeller ikke med
    assert c["color"] != "#C0392B", c["status"]


def test_kpi_kontrakten():
    """Fund 10: kpi() skriver direkte til data.json's kpis-kontrakt og var utestet."""
    tom = vo2_dose.kpi(None)
    assert tom == {"value": "—", "unit": "min", "sub": "VO2-dosis", "color": "#6B7A88"}
    c = vo2_dose.card([_ride("2027-03-16", 840)], FIX, today=date(2027, 3, 18))
    k = vo2_dose.kpi(c)
    assert k["value"] == "14" and k["unit"] == "min" and k["color"] == c["color"]
    assert "mål 15 min" in k["sub"] and "pas" in k["sub"]
    hvile = vo2_dose.kpi(vo2_dose.card([], FIX, today=date(2027, 3, 25)))
    assert hvile["sub"] == "restitutionsuge — mål 0" and hvile["value"] == "0"
