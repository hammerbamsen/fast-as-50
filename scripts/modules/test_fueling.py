# -*- coding: utf-8 -*-
"""Tests for fueling.py (Fase 2 — ernærings-substans, standarddefaults)."""
from . import fueling as fu


def test_medoc_defaults_hot_climate_bumps_fluid_and_sodium():
    t = fu.fueling_targets("medoc")
    assert t["race"] == "Marathon du Médoc"
    assert t["climate"] == "hot"
    # hot -> 1.25x fluid, 1.3x sodium vs. base range
    assert t["fluid_ml_per_h"]["low"] == round(500 * 1.25)
    assert t["fluid_ml_per_h"]["high"] == round(750 * 1.25)
    assert t["sodium_mg_per_h"]["low"] == round(300 * 1.3)
    assert t["sodium_mg_per_h"]["high"] == round(700 * 1.3)
    assert t["carb_g_per_h"] == {"low": 60, "high": 90}


def test_stelvio_defaults_variable_climate_no_adjust():
    t = fu.fueling_targets("stelvio")
    assert t["race"] == "Stelvio"
    assert t["climate"] == "variable"
    assert t["fluid_ml_per_h"] == {"low": 500, "high": 750}
    assert t["sodium_mg_per_h"] == {"low": 300, "high": 700}
    assert t["duration_h"] == 7.0
    assert t["total_carb_g"] == {"low": round(60 * 7.0), "high": round(90 * 7.0)}


def test_short_event_lowers_carb_target():
    t = fu.fueling_targets(None, duration_h=1.5, climate="variable")
    assert t["carb_g_per_h"] == {"low": 30, "high": 60}


def test_explicit_override_wins_over_race_defaults():
    t = fu.fueling_targets("medoc", duration_h=3.0, climate="cool")
    assert t["duration_h"] == 3.0
    assert t["climate"] == "cool"
    assert t["fluid_ml_per_h"]["low"] == round(500 * 0.85)


def test_unknown_race_key_falls_back_to_generic():
    t = fu.fueling_targets("unknown_race")
    assert t["race"] == "unknown_race"
    assert t["duration_h"] == 3.0
    assert t["climate"] == "variable"


def test_all_race_targets_returns_both_keys():
    all_t = fu.all_race_targets()
    assert set(all_t.keys()) == {"medoc", "stelvio"}
    assert all_t["medoc"]["race"] == "Marathon du Médoc"
    assert all_t["stelvio"]["race"] == "Stelvio"


def test_note_flags_standard_defaults_not_calibrated():
    t = fu.fueling_targets("medoc")
    assert "ikke individuelt kalibreret" in t["note"]
