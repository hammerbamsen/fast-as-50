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
    f = F.build(_plan(), date(2026, 9, 25), weight_avg7=72.0, week_num=3)
    assert f["phase"] == "TRANSITION" and f["phaseTarget"] == 278
    assert f["status"] == "ok" and f["color"] == F.GREEN
    assert f["wkg"] == 3.86


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
    """plan.json: ftpHistory er seedet og der er en FTP-test tor 24/9."""
    assert F.history(PLAN), "ftpHistory mangler i plan.json"
    assert F.history(PLAN)[-1]["ftpW"] == PLAN["athletes"]["kennet"]["zones"]["ftpW"]
    assert F.next_test(PLAN, date(2026, 9, 21)) == "2026-09-24"
    f = F.build(PLAN, date(2026, 9, 21), weight_avg7=72.0, week_num=3)
    assert f["phaseTarget"] == 278 and f["seasonTarget"] == 320 and len(f["phases"]) == 6


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
