# -*- coding: utf-8 -*-
"""Tests for plan_coherence.py (T5 — plan-kohærens-tjek)."""
from . import plan_coherence as pc

BASE_PLAN = {
    "program": {"start": "2026-06-01", "totalWeeks": 2},
    "athletes": {
        "kennet": {
            "actualsThroughWeek": 1,
            "days": [
                {"date": "2026-06-01", "entries": [{"id": "e1", "workout": {"type": "Run", "name": "Lang løb"}}]},
                {"date": "2026-06-03", "entries": [{"id": "e2", "workout": {"type": "Run", "name": "Tempo"}}]},
                {"date": "2026-06-08", "entries": [{"id": "e3", "workout": {"type": "Ride", "name": "Cykel Z2"}}]},
            ],
        }
    },
}


def test_wales_case_unplanned_discipline_flagged():
    """Fundament-reviewets kerneeksempel: uge uden cykel i planen, men en
    logget cykeltur -> WARN-flag for den uge."""
    activities = [
        {"start_date_local": "2026-06-02T09:00:00", "type": "VirtualRide", "moving_time": 3600},
    ]
    flags = pc.coherence_flags(BASE_PLAN, activities)
    assert len(flags) == 1
    assert flags[0]["week"] == 1
    assert flags[0]["rule"] == "plan_actual_mismatch"
    assert flags[0]["level"] == "WARN"
    assert "bike" in flags[0]["msg"]


def test_planned_discipline_matches_no_flag():
    """Aktivitet der matcher en planlagt disciplin -> intet flag."""
    activities = [
        {"start_date_local": "2026-06-01T08:00:00", "type": "Run", "moving_time": 2700},
    ]
    assert pc.coherence_flags(BASE_PLAN, activities) == []


def test_short_activity_filtered_as_noise():
    """Aktivitet under MIN_ACTIVITY_SECONDS (fx GPS-test) -> ingen flag."""
    activities = [
        {"start_date_local": "2026-06-04T07:00:00", "type": "Ride", "moving_time": 45},
    ]
    assert pc.coherence_flags(BASE_PLAN, activities) == []


def test_future_week_beyond_actuals_not_checked():
    """Uger efter actualsThroughWeek er fremtid -> ingen flag, selv med
    umatchet disciplin."""
    activities = [
        {"start_date_local": "2026-06-09T07:00:00", "type": "Swim", "moving_time": 1800},
    ]
    assert pc.coherence_flags(BASE_PLAN, activities) == []


def test_empty_or_missing_activities():
    assert pc.coherence_flags(BASE_PLAN, []) == []
    assert pc.coherence_flags(BASE_PLAN, None) == []


def test_malformed_plan_degrades_gracefully():
    assert pc.coherence_flags({}, [{"start_date_local": "2026-06-01T08:00:00",
                                     "type": "Ride", "moving_time": 3600}]) == []


def test_signature_deterministic():
    flags = [{"week": 1, "rule": "plan_actual_mismatch", "level": "WARN", "msg": "x"}]
    assert pc.signature(flags) == "1:plan_actual_mismatch"
    assert pc.signature([]) == ""
