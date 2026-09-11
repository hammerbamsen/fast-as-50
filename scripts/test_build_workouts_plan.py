# -*- coding: utf-8 -*-
"""Tests for scripts/build_workouts.py::make_plan — ren logik, ingen netværk.

Køres af CI: python3 -m pytest scripts/modules/ scripts/test_*.py -q
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_workouts as bw  # noqa: E402


def _plan(days):
    return {"athletes": {"kennet": {"days": days}}}


def _wo(name="Løb Z2 45 min"):
    return {"name": name, "type": "Run", "moving_time": 2700, "description": "- Base 45m"}


def test_ryddet_dag_kommer_med_som_hviledag(monkeypatch):
    """En dag med entries: [] skal give en (dato, None, note)-tuple, så
    run_plan besøger datoen og sletter gamle events (QA-fund 9/9-2026)."""
    monkeypatch.setattr(bw, "load_plan_json", lambda: _plan([
        {"date": "2026-10-01", "entries": [{"workout": _wo()}]},
        {"date": "2026-10-02", "entries": []},
    ]))
    out = bw.make_plan()
    assert len(out) == 2
    assert out[1] == (date(2026, 10, 2), None, "ingen pas i planen")


def test_ryddet_dag_bevarer_dagens_note(monkeypatch):
    monkeypatch.setattr(bw, "load_plan_json", lambda: _plan([
        {"date": "2026-10-02", "entries": [], "note": "Fri — rejsedag"},
    ]))
    assert bw.make_plan() == [(date(2026, 10, 2), None, "Fri — rejsedag")]


def test_dag_uden_entries_noegle(monkeypatch):
    """Manglende 'entries' må ikke kaste — dagen behandles som ryddet."""
    monkeypatch.setattr(bw, "load_plan_json", lambda: _plan([{"date": "2026-10-02"}]))
    assert bw.make_plan() == [(date(2026, 10, 2), None, "ingen pas i planen")]


def test_hviledag_og_pas_uaendret(monkeypatch):
    """Eksisterende adfærd: entry med workout=None er en hviledag; valgfrit
    pas får '(valgfri)' i navnet uden at røre plan.json."""
    monkeypatch.setattr(bw, "load_plan_json", lambda: _plan([
        {"date": "2026-10-03", "entries": [{"workout": None, "note": "Hviledag"}]},
        {"date": "2026-10-04", "entries": [{"workout": _wo(), "optional": True}]},
    ]))
    out = bw.make_plan()
    assert out[0] == (date(2026, 10, 3), None, "Hviledag")
    assert out[1][1]["name"] == "Løb Z2 45 min (valgfri)"


def test_rigtig_plan_har_de_ryddede_dage():
    """Mod den faktiske plan.json: ryddede dage skal være med i listen, så
    byg-scriptet rydder dem i Intervals. Blok 11 (11/9-2026): planen løber til
    3/1-2027; juleaftensdag har kun styrke og 1. juledag (fre 25/12) er ryddet."""
    out = {dt: wo for dt, wo, _ in bw.make_plan()}
    d = date(2026, 12, 25)
    assert d in out and out[d] is None, "25/12 mangler i make_plan()"
    assert date(2027, 1, 3) in out, "planen skal løbe til søn 3/1-2027"
