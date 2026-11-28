# -*- coding: utf-8 -*-
"""Tests for modules/ftp_track.py (blok 13). Ren logik."""
import copy
import json
from datetime import date
from pathlib import Path

import pytest

from modules import ftp_track as F

ROOT = Path(__file__).resolve().parent.parent.parent
PLAN = json.loads((ROOT / "data" / "plan.json").read_text(encoding="utf-8"))


def _plan(ftp=278, hist=None, phases=None, days=None):
    return {
        "athletes": {"kennet": {"zones": {"ftpW": ftp}, "ftpHistory": hist or [],
                                "days": days or []}},
        "season2027": {"ftpStart": 278, "ftpTarget": 320,
                       "phases": phases if phases is not None else [
                           {"name": "TRANSITION", "weekFrom": 1, "weekTo": 8, "ftpTarget": 278, "wkgTarget": 3.97},
                           {"name": "BASE", "weekFrom": 9, "weekTo": 22, "ftpTarget": 292, "wkgTarget": 4.29},
                       ]},
    }


def test_build_status_green_when_at_target():
    """28/11-2026: W/kg er hovedtallet naar baade vaegt og wkgTarget findes.
    Samme watt kan vaere baade paa og under maal alt efter vaegten."""
    f = F.build(_plan(), date(2026, 9, 25), weight_avg7=72.0, week_num=3)
    assert f["phase"] == "TRANSITION" and f["phaseTarget"] == 278
    assert f["wkg"] == 3.86 and f["primary"] == "wkg"
    # wkgTarget i fixturen er 3.97; 3.86 er under, men inden for 3 % -> warn
    assert f["status"] == "warn"
    # lettere rytter, samme watt -> paa maal
    let = F.build(_plan(), date(2026, 9, 25), weight_avg7=70.0, week_num=3)
    assert let["wkg"] == 3.97 and let["status"] == "ok" and let["color"] == F.GREEN
    # uden vaegt falder kortet tilbage paa watt
    uden = F.build(_plan(), date(2026, 9, 25), week_num=3)
    assert uden["primary"] == "ftp" and uden["status"] == "ok"


def test_build_status_warn_and_bagud():
    assert F.build(_plan(ftp=285), date(2026, 11, 5), week_num=9)["status"] == "warn"     # 285 >= 292*0.97
    assert F.build(_plan(ftp=270), date(2026, 11, 5), week_num=9)["status"] == "bagud"


def test_build_without_target_is_neutral():
    f = F.build(_plan(phases=[]), date(2026, 9, 25), week_num=3)
    assert f["status"] == "none" and f["color"] == F.NEUTRAL and f["phaseTarget"] is None


def test_next_test_finds_library_id_and_name():
    days = [
        {"date": "2026-09-20", "entries": [{"libraryId": "test_ftp20", "workout": {"name": "x", "type": "Ride"}}]},
        {"date": "2026-09-24", "entries": [{"libraryId": "test_ftp20", "workout": {"name": "FaF 0 Test - FTP 20 min", "type": "Ride"}}]},
        {"date": "2027-02-18", "entries": [{"workout": {"name": "FTP-TEST 20 min", "type": "Ride"}}]},
    ]
    p = _plan(days=days)
    assert F.next_test(p, date(2026, 9, 21)) == "2026-09-24"      # ikke den der er passeret
    assert F.next_test(p, date(2026, 9, 25)) == "2027-02-18"
    assert F.next_test(p, date(2027, 3, 1)) is None


def test_record_appends_only_on_change():
    p = _plan(hist=[{"date": "2026-07-28", "ftpW": 278, "source": "test"}])
    assert F.record(p, 278, date(2026, 9, 24)) is False
    assert F.record(p, 290, date(2026, 9, 24)) is True
    assert p["athletes"]["kennet"]["ftpHistory"][-1] == {"date": "2026-09-24", "ftpW": 290, "source": "set_zones"}
    assert F.history(p)[-1]["ftpW"] == 290


def test_kpi_text():
    f = F.build(_plan(days=[{"date": "2026-09-24", "entries": [{"libraryId": "test_ftp20", "workout": {"name": "t", "type": "Ride"}}]}]),
                date(2026, 9, 21), weight_avg7=72.2, week_num=3)
    k = F.kpi(f)
    assert k["value"] == "278" and k["unit"] == "W"
    assert "3,85 W/kg" in k["sub"] and "mål 278 (TRANSITION)" in k["sub"] and "test 24/9" in k["sub"]
    assert F.kpi({})["value"] == "—"


def test_real_plan_has_history_and_test():
    """plan.json: ftpHistory er seedet og der ligger en FTP-test i uge 41.
    Flyttet 24/9 fra uge 39 til tor 8/10 (forslag 2026-09-24-styrke-lor-svom-fre-ftp).
    Datoen låses ikke — testen kan flyttes inden for ugen."""
    assert F.history(PLAN), "ftpHistory mangler i plan.json"
    assert F.history(PLAN)[-1]["ftpW"] == PLAN["athletes"]["kennet"]["zones"]["ftpW"]
    nt = F.next_test(PLAN, date(2026, 9, 21))
    assert nt and "2026-10-05" <= nt <= "2026-10-11", nt
    # Tallene laases ikke: faserne er rekalibreret flere gange (320 -> 295 den
    # 28/11-2026) og fasenavnene skiftede til Friels ved samme lejlighed.
    # QA 28/11 paaviste at foerste udgave af denne test var en tautologi: den
    # sammenlignede phase_for med sig selv, saa mutationer der fik phase_for til
    # altid at returnere foerste eller sidste fase slap igennem. Faselisten
    # hentes nu uafhaengigt af phase_for, og der assertes baand, ikke vaerdier.
    f = F.build(PLAN, date(2026, 9, 21), weight_avg7=72.0, week_num=3)
    faser = (PLAN["season2027"] or {})["phases"]
    assert faser, "ingen faser i planen"
    tds = PLAN["programs"]["tds-2027"]
    for w in range(1, tds["totalWeeks"] + 1):
        egen = [x for x in faser if x["weekFrom"] <= w <= x["weekTo"]]
        assert len(egen) == 1, f"uge {w} rammer {len(egen)} faser"
        # phase_for maa ikke kunne ramme en fase ugen ikke ligger i
        assert F.phase_for(PLAN, w) is egen[0], f"phase_for ramte forkert fase i uge {w}"
    assert f["phaseTarget"] == F.phase_for(PLAN, 3)["ftpTarget"]
    # sidste fase ER toppen, og saesonmaalet er den
    assert faser[-1]["ftpTarget"] == max(x["ftpTarget"] for x in faser)
    assert f["seasonTarget"] == faser[-1]["ftpTarget"]
    # plausibilitetsbaand: testen skal ogsaa fange at ALLE maal faldt til 0
    assert all(150 < x["ftpTarget"] < 500 for x in faser), "ftpTarget uden for 150-500"
    assert all(2.0 < x["wkgTarget"] < 7.0 for x in faser), "wkgTarget uden for 2-7"
    # maalene maa ikke falde hen over saesonen
    assert all(x["ftpTarget"] <= y["ftpTarget"] for x, y in zip(faser, faser[1:]))


def test_set_zones_records_history():
    """edit_apply set_zones med ny ftpW skriver en ftpHistory-post."""
    from modules import edit_apply
    p = copy.deepcopy(PLAN)
    raw = json.dumps(p, ensure_ascii=False)
    res = edit_apply.apply_edit(raw, "set_zones", "zones", {"ftpW": 290}, confirmed_warn=True)
    assert res["status"] == "ok", res
    new = json.loads(res["new_plan_raw"])
    assert new["athletes"]["kennet"]["zones"]["ftpW"] == 290
    assert new["athletes"]["kennet"]["ftpHistory"][-1]["ftpW"] == 290
