# -*- coding: utf-8 -*-
"""Tests for martin_signals.py — relevansfilter og md-format."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import martin_signals as ms


def mk(days):
    return {"program": {"start": "2026-06-01", "totalWeeks": 14},
            "athletes": {"kennet": {"days": days}}}


def d(d_iso, *wos):
    return {"date": d_iso, "entries": [{"workout": w} for w in wos]}


EASY30 = {"name": "Cykel Z2 let", "type": "Ride", "moving_time": 1800}
EASY45 = {"name": "Cykel Z2 let", "type": "Ride", "moving_time": 2700}
VO2 = {"name": "Løb VO2 5×3 Z4", "type": "Run", "moving_time": 2700}
LONG = {"name": "Cykel Z2 lang", "type": "Ride", "moving_time": 3 * 3600}


def test_small_easy_change_is_noise():
    old = mk([d("2026-06-04", EASY30)])
    new = mk([d("2026-06-05", EASY30), d("2026-06-04")])
    assert ms.build_signal(old, new, "move", ["2026-06-04", "2026-06-05"]) is None


def test_hard_session_added_signals():
    old = mk([d("2026-06-04")])
    new = mk([d("2026-06-04", VO2)])
    sig = ms.build_signal(old, new, "add", ["2026-06-04"])
    assert sig and "VO2" in sig and "[hårdt]" in sig and "hviledag" in sig


def test_long_session_moved_signals():
    old = mk([d("2026-06-04", LONG), d("2026-06-06")])
    new = mk([d("2026-06-04"), d("2026-06-06", LONG)])
    sig = ms.build_signal(old, new, "move", ["2026-06-04", "2026-06-06"])
    assert sig and sig.count("[langt]") >= 2 and "uge 1" in sig


def test_duration_delta_45min_signals():
    old = mk([d("2026-06-04", EASY30)])
    new = mk([d("2026-06-04", EASY30, EASY45)])
    sig = ms.build_signal(old, new, "add", ["2026-06-04"])
    assert sig is not None


def test_eva_edits_never_signal():
    old = mk([d("2026-06-04")])
    new = mk([d("2026-06-04", VO2)])
    assert ms.build_signal(old, new, "add", ["2026-06-04"], athlete="eva") is None


def test_append_creates_header_and_appends():
    sig = "\n### Planændring 07/07 15:00\n- test\n"
    md = ms.append_signal("", sig)
    assert md.startswith("# Signaler til Martin")
    md2 = ms.append_signal(md, sig)
    assert md2.count("### Planændring") == 2
    assert md2.count("# Signaler til Martin —") == 1
