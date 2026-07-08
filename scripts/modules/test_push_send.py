# -*- coding: utf-8 -*-
"""Tests for U2 push-besked-logik. Køres af ci-pytest.yml (X4)."""
from . import push_send


def _plan():
    return {"athletes": {
        "kennet": {"days": [
            {"date": "2026-07-08", "entries": [
                {"id": "k1", "workout": {"name": "Løb Z2 45 min", "type": "Run"}}]},
            {"date": "2026-07-09", "entries": [
                {"id": "k2", "note": "Hviledag"}]},
            {"date": "2026-07-10", "entries": [
                {"id": "k3", "workout": {"name": "Svøm 2000m", "type": "Swim"}},
                {"id": "k4", "workout": {"name": "Styrke A", "type": "WeightTraining"}}]},
        ]},
        "eva": {"days": [
            {"date": "2026-07-08", "entries": [
                {"id": "e1", "workout": {"name": "Løbetur — 30 min", "type": "Run"}}]},
        ]},
    }}


# ── workouts_for / build_daily_message ───────────────────────────

def test_single_workout_message():
    m = push_send.build_daily_message(_plan(), "kennet", "2026-07-08")
    assert m["title"] == "I dag: Løb Z2 45 min"
    assert m["tag"] == "fast50-daily"
    assert m["athlete"] == "kennet"


def test_rest_day_returns_none():
    assert push_send.build_daily_message(_plan(), "kennet", "2026-07-09") is None


def test_multiple_workouts_joined():
    m = push_send.build_daily_message(_plan(), "kennet", "2026-07-10")
    assert m["title"] == "I dag: Svøm 2000m + Styrke A"


def test_eva_url_points_to_eva_page():
    m = push_send.build_daily_message(_plan(), "eva", "2026-07-08")
    assert m["url"] == "eva.html"


def test_kennet_url_root():
    m = push_send.build_daily_message(_plan(), "kennet", "2026-07-08")
    assert m["url"] == "./"


def test_unknown_athlete_none():
    assert push_send.build_daily_message(_plan(), "nobody", "2026-07-08") is None


def test_no_day_match_none():
    assert push_send.build_daily_message(_plan(), "kennet", "2026-12-31") is None


# ── dead-subscription-håndtering ─────────────────────────────────

def test_is_dead_status():
    assert push_send.is_dead_status(410)
    assert push_send.is_dead_status(404)
    assert not push_send.is_dead_status(201)
    assert not push_send.is_dead_status(500)   # midlertidig — IKKE død


def test_prune_removes_dead():
    subs = [{"endpoint": "a"}, {"endpoint": "b"}, {"endpoint": "c"}]
    out = push_send.prune_subscriptions(subs, {"b"})
    assert [s["endpoint"] for s in out] == ["a", "c"]


def test_subs_for_athlete():
    subs = [{"endpoint": "a", "athlete": "kennet"},
            {"endpoint": "b", "athlete": "eva"}]
    assert len(push_send.subs_for_athlete(subs, "kennet")) == 1


# ── upsert (dedup + bevar added-dato) ───────────────────────────

def test_upsert_new():
    out = push_send.upsert_subscription([], {"endpoint": "a", "athlete": "eva"}, today="2026-07-08")
    assert len(out) == 1 and out[0]["added"] == "2026-07-08"


def test_upsert_dedup_keeps_added():
    subs = [{"endpoint": "a", "athlete": "eva", "added": "2026-06-01"}]
    out = push_send.upsert_subscription(subs, {"endpoint": "a", "athlete": "eva", "keys": {"x": 1}}, today="2026-07-08")
    assert len(out) == 1
    assert out[0]["added"] == "2026-06-01"   # bevaret
    assert out[0]["keys"] == {"x": 1}        # opdateret


def test_upsert_different_endpoint_appends():
    subs = [{"endpoint": "a", "athlete": "eva", "added": "2026-06-01"}]
    out = push_send.upsert_subscription(subs, {"endpoint": "b", "athlete": "eva"}, today="2026-07-08")
    assert len(out) == 2
