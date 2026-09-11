# -*- coding: utf-8 -*-
"""Tests for tidsreglen i modules/outlook_times.py (blok 8) — én kilde for
sync_outlook.py (ugesynk) og apply_edit.py (plan-edit): schedule_day(workouts,
overrides) — styrke 06:30 først, +15 min mellem pas, aldrig overlap,
timeOverrides pr. pas.

Kør: python3 -m pytest scripts/modules/test_outlook_times.py -q
"""
import os
import sys
from datetime import datetime

from modules import outlook_times as so


def wo(typ, mins, name=None, day="2026-09-14"):
    return {"type": typ, "moving_time": mins * 60, "name": name or typ,
            "start_date_local": f"{day}T00:00:00"}


def times(sched):
    return [(w["type"], s.strftime("%H:%M")) for w, s in sched]


def _overlaps(sched):
    spans = sorted((s, s + so._duration(w)) for w, s in sched)
    return any(spans[i][1] > spans[i + 1][0] for i in range(len(spans) - 1))


# ── Enkelt pas ─────────────────────────────────────────────────────────────

def test_single_strength_starts_0630_and_defaults():
    assert times(so.schedule_day([wo("WeightTraining", 25)], None)) == [("WeightTraining", "06:30")]
    assert times(so.schedule_day([wo("Ride", 60)], None)) == [("Ride", "07:00")]
    assert times(so.schedule_day([wo("Swim", 45)], None)) == [("Swim", "06:00")]
    assert times(so.schedule_day([wo("Hike", 45)], None)) == [("Hike", "06:00")]   # ukendt type -> 06:00
    assert so.schedule_day([], None) == []


def test_single_override_tuple_and_dict():
    assert times(so.schedule_day([wo("Ride", 60)], (16, 0))) == [("Ride", "16:00")]
    assert times(so.schedule_day([wo("Ride", 60)], {"ride": (6, 15)})) == [("Ride", "06:15")]
    # dict-override for en anden disciplin rører ikke passet
    assert times(so.schedule_day([wo("Ride", 60)], {"run": (7, 0)})) == [("Ride", "07:00")]
    # start_date_local styrer datoen
    (w, s), = so.schedule_day([wo("Run", 40, day="2026-09-20")], None)
    assert s == datetime(2026, 9, 20, 6, 30)


# ── Flere pas samme dag ────────────────────────────────────────────────────

def test_strength_first_then_gap_15():
    sched = so.schedule_day([wo("Run", 30), wo("WeightTraining", 25)], None)
    assert times(sched) == [("WeightTraining", "06:30"), ("Run", "07:15")]   # 25 min -> min 30: 07:00, +15
    assert not _overlaps(sched)


def test_chain_three_sessions_min_30():
    sched = so.schedule_day([wo("Swim", 20), wo("WeightTraining", 60), wo("Ride", 45)], None)
    # styrke 06:30-07:30 · swim (min 30 min) 07:45-08:15 · ride 08:30
    assert times(sched) == [("WeightTraining", "06:30"), ("Swim", "07:45"), ("Ride", "08:30")]
    assert not _overlaps(sched)


def test_override_respected_and_free_session_moves():
    # Styrke flyttet til 16:00 (override) — løbet får sin standardtid 06:30
    sched = so.schedule_day([wo("WeightTraining", 25), wo("Run", 40)], {"weighttraining": (16, 0)})
    assert times(sched) == [("Run", "06:30"), ("WeightTraining", "16:00")]
    # Løb med override 06:40 der ville overlappe styrke 06:30-06:55: styrke (uden override) flyttes
    sched2 = so.schedule_day([wo("WeightTraining", 25), wo("Run", 40)], {"run": (6, 40)})
    assert times(sched2) == [("Run", "06:40"), ("WeightTraining", "07:35")]   # 06:40+40 = 07:20, +15
    # Cykel med override 07:00 lige efter styrke 06:30-07:00: ingen overlap -> ingen flytning
    sched3 = so.schedule_day([wo("WeightTraining", 25), wo("Ride", 60)], {"ride": (7, 0)})
    assert times(sched3) == [("WeightTraining", "06:30"), ("Ride", "07:00")]
    assert not _overlaps(sched2)


def test_tuple_override_for_two_sessions_never_overlaps():
    # Dagsdækkende (8, 30) gælder begge — kun ét pas kan ligge der; det andet kædes efter
    sched = so.schedule_day([wo("Run", 90, name="CPH HALF"), wo("WeightTraining", 25)], (8, 30))
    assert times(sched) == [("WeightTraining", "08:30"), ("Run", "09:15")]   # styrke 30 min, +15
    assert not _overlaps(sched)


def test_free_session_skips_past_fixed_block():
    # Styrke 06:30-07:00, løb ville kædes 07:15 — men cyklen har override 07:00-08:00 -> løb 08:15
    sched = so.schedule_day([wo("WeightTraining", 25), wo("Run", 30), wo("Ride", 60)], {"ride": (7, 0)})
    assert times(sched) == [("WeightTraining", "06:30"), ("Ride", "07:00"), ("Run", "08:15")]
    assert not _overlaps(sched)


def test_event_body_uses_schedule_and_duration():
    (w, s), = so.schedule_day([wo("WeightTraining", 25, name="Styrke A · 2 runder")], None)
    ev = so.event_body(w, s)
    assert ev["subject"] == "💪 Styrke A · 2 runder"
    assert ev["start"]["dateTime"] == "2026-09-14T06:30:00" and ev["end"]["dateTime"] == "2026-09-14T07:00:00"
    assert ev["start"]["timeZone"] == "Europe/Copenhagen" and ev["categories"] == ["Træning"]
    ev2 = so.event_body(wo("Ride", 0), datetime(2026, 9, 14, 7, 0))
    assert ev2["end"]["dateTime"] == "2026-09-14T08:00:00"   # uden moving_time: 60 min som før


def test_entries_and_overrides_from_plan_shape():
    ov = so.normalize_overrides({"2026-09-14": [6, 0], "2026-09-15": {"Run": [7, 0], "WeightTraining": [16, 0]}})
    assert ov == {"2026-09-14": (6, 0), "2026-09-15": {"run": (7, 0), "weighttraining": (16, 0)}}
    entries = [{"id": "a", "workout": {"name": "Cykel Z2 45 min", "type": "Ride", "moving_time": 2700}},
               {"id": "b", "workout": None, "note": "hvile"},
               {"id": "c", "workout": {"name": "Styrke 25 min", "type": "WeightTraining", "moving_time": 1500}}]
    ws = so.workouts_from_entries("2026-09-14", entries)
    assert [w["name"] for w in ws] == ["Cykel Z2 45 min", "Styrke 25 min"] and ws[0]["start_date_local"] == "2026-09-14T00:00:00"
    assert times(so.schedule_day(ws, ov.get("2026-09-14"))) == [("WeightTraining", "06:00"), ("Ride", "06:45")]
    assert times(so.schedule_day(ws, None)) == [("WeightTraining", "06:30"), ("Ride", "07:15")]


def test_sync_outlook_script_imports_same_source():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".github", "workflows", "scripts"))
    import sync_outlook
    assert sync_outlook.schedule_day is so.schedule_day and sync_outlook.event_body is so.event_body


def test_sync_outlook_parse_weeks():
    """Rækkesynk (11/9-2026): '3', '3-17' og 'all' — og ugyldige uger fanges."""
    import pytest
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".github", "workflows", "scripts"))
    import sync_outlook
    assert sync_outlook.parse_weeks("3", 51) == [3]
    assert sync_outlook.parse_weeks("3-5", 51) == [3, 4, 5]
    assert sync_outlook.parse_weeks("all", 4) == [1, 2, 3, 4]
    for bad in ("0", "52", "5-3", "x"):
        with pytest.raises((AssertionError, ValueError)):
            sync_outlook.parse_weeks(bad, 51)
