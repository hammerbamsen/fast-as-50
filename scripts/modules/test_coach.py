# -*- coding: utf-8 -*-
"""Tests for coach.py — distance-flag i coach-tekst og AI-prompt (rettet 7/8-2026).

build_distance_focus_line() bruges af generate_coach_speech() (hårdkodet tekst),
build_distance_prompt_line() af generate_ai_assessment() (AI-prompt-kontekst).
Begge er udtrukket som selvstændige funktioner så de kan testes uden en fuld
week_sessions-liste eller et Anthropic-API-kald.
"""
from datetime import date

import pytest

from . import coach

TODAY_WEEKDAY = date.today().weekday()


# ── build_distance_focus_line (coach-tekst) ─────────────────────────────

def test_focus_line_flags_shortfall_with_real_numbers():
    session = {
        "label": "OW-svøm 2500m SAMMENHÆNGENDE (Christiansborg-generalprøve)",
        "planned_distance_m": 2500, "actual_distance_m": 1390,
    }
    line = coach.build_distance_focus_line(session)
    assert line is not None
    assert "1390 af 2500m" in line
    assert "56%" in line
    assert "under målet" in line


def test_focus_line_none_when_goal_met():
    session = {"label": "Svøm 2000m teknisk", "planned_distance_m": 2000, "actual_distance_m": 2100}
    assert coach.build_distance_focus_line(session) is None


def test_focus_line_none_without_distance_target():
    session = {"label": "Svøm let 30 min recovery", "planned_distance_m": None, "actual_distance_m": 1200}
    assert coach.build_distance_focus_line(session) is None


def test_focus_line_none_when_no_distance_data_reported():
    """Garmin/Intervals har ikke rapporteret distance -> intet flag, ikke en falsk alarm."""
    session = {"label": "OW-svøm 2500m", "planned_distance_m": 2500, "actual_distance_m": None}
    assert coach.build_distance_focus_line(session) is None


def test_focus_line_none_when_no_session():
    assert coach.build_distance_focus_line(None) is None


def test_focus_line_respects_custom_threshold():
    session = {"label": "Svøm 2000m", "planned_distance_m": 2000, "actual_distance_m": 1900}  # 95%
    assert coach.build_distance_focus_line(session, shortfall_threshold=0.80) is None
    assert coach.build_distance_focus_line(session, shortfall_threshold=0.98) is not None


# ── build_distance_prompt_line (AI-prompt) ──────────────────────────────

def test_prompt_line_includes_numbers_and_instruction():
    session = {"planned_distance_m": 2500, "actual_distance_m": 1390}
    line = coach.build_distance_prompt_line(session)
    assert "1390 af 2500" in line
    assert "56%" in line
    assert "EKSPLICIT" in line


def test_prompt_line_empty_without_distance_target():
    assert coach.build_distance_prompt_line({"planned_distance_m": None, "actual_distance_m": 1200}) == ""


def test_prompt_line_empty_when_no_distance_data_reported():
    assert coach.build_distance_prompt_line({"planned_distance_m": 2500, "actual_distance_m": None}) == ""


def test_prompt_line_empty_when_no_session():
    assert coach.build_distance_prompt_line(None) == ""


# ── generate_coach_speech — end-to-end tekst (samme scenarie som sagen) ─

def _base_speech_kwargs(today_session, week_sessions):
    return dict(
        week_num=10, weekday=TODAY_WEEKDAY, streak=3, af_this_week=2,
        today_session=today_session, block_type="BUILD", week_focus="Build-uge",
        ctl=55, tsb=-8, weight=71.5, sleep=7.2, compliance=85, tss_act=100,
        planned=120, remaining_sessions=[], week_sessions=week_sessions,
        days_completed=TODAY_WEEKDAY,
    )


def test_generate_coach_speech_mentions_distance_shortfall():
    today_session = {
        "today": True, "done": True, "disc": "openwater",
        "label": "OW-svøm 2500m SAMMENHÆNGENDE (Christiansborg-generalprøve)",
        "planned_distance_m": 2500, "actual_distance_m": 1390,
    }
    speech, _highlight = coach.generate_coach_speech(
        **_base_speech_kwargs(today_session, [today_session]))
    assert "1390 af 2500m" in speech
    assert "56%" in speech
    assert "under målet" in speech


def test_generate_coach_speech_silent_when_no_distance_target():
    today_session = {
        "today": True, "done": True, "disc": "bike", "label": "Cykel Z2 90 min",
        "planned_distance_m": None, "actual_distance_m": None,
    }
    speech, _highlight = coach.generate_coach_speech(
        **_base_speech_kwargs(today_session, [today_session]))
    assert "under målet" not in speech


# ── Enhed pr. disciplin (8/8-2026) ──────────────────────────────────────
# Da km-mål blev indført for løb/cykel, nåede distance-funktionerne pludselig
# discipliner de var skrevet til svøm for. Uden disse vagter beskrives et løb
# som "21000 af 29000m".

def test_distance_focus_line_uses_km_for_run():
    line = coach.build_distance_focus_line({
        'label': 'Lang løb Z2 29 km', 'disc': 'run',
        'planned_distance_m': 29000, 'actual_distance_m': 21000.0,
    })
    assert '21,0 af 29,0 km' in line
    assert '29000' not in line


def test_distance_focus_line_keeps_meters_for_swim():
    """Svøm-formuleringen fra 7/8-2026 var korrekt og må ikke ændre sig."""
    line = coach.build_distance_focus_line({
        'label': 'OW-svøm 2500m', 'disc': 'openwater',
        'planned_distance_m': 2500, 'actual_distance_m': 1390.0,
    })
    assert '1390 af 2500m' in line


def test_distance_prompt_line_uses_km_for_run():
    line = coach.build_distance_prompt_line({
        'label': 'Lang løb Z2 29 km', 'disc': 'run',
        'planned_distance_m': 29000, 'actual_distance_m': 28227.0,
    })
    assert '28,2 af 29,0 km' in line
    assert '28227' not in line


# ── Aerobt flag i coach-teksten (26/8-2026) ─────────────────────────────
# Flaget beregnes i decoupling.py, men skal også overleve HELE vejen ud i
# den deterministiske coach-tale — ellers forsvinder det tavst hver gang
# ANTHROPIC_API_KEY mangler eller AI-kaldet fejler, og det er præcis de
# situationer hvor et regelbaseret signal er mest værd.

def test_coach_speech_viser_aerobt_flag():
    today_session = {
        "today": True, "done": True, "disc": "run", "label": "Løb Z2 18 km",
        "planned_distance_m": None, "actual_distance_m": None,
    }
    kwargs = _base_speech_kwargs(today_session, [today_session])
    kwargs["decoupling_note"] = (
        "Løbeturen 2026-08-25 (snitpuls 151) kostede 6,5 % mere puls pr. meter "
        "end medianen af de seneste 4 sammenlignelige pas."
    )
    speech, _highlight = coach.generate_coach_speech(**kwargs)
    assert "Aerobt" in speech
    assert "151" in speech
    assert "6,5 %" in speech


def test_coach_speech_tier_uden_aerobt_flag():
    """Ingen flag = ingen linje. Tavshed er den rigtige default."""
    today_session = {
        "today": True, "done": True, "disc": "run", "label": "Løb Z2 18 km",
        "planned_distance_m": None, "actual_distance_m": None,
    }
    speech, _highlight = coach.generate_coach_speech(
        **_base_speech_kwargs(today_session, [today_session]))
    assert "Aerobt" not in speech


# ── Ingen TSS-% i RACE/RECOVERY/TAPER (blok 9, 9/9-2026) ────────────────
# I en lav-belastningsuge er lav TSS planen. "N procent af ugens TSS er i hus"
# og "X af Y TSS" læses som et efterslæb — de udelades, én neutral linje i stedet.

def _low_load_kwargs(block_type, compliance=40, done=False):
    today_session = {"today": True, "done": done, "disc": "bike", "label": "Cykel Z2 60 min",
                     "planned_distance_m": None, "actual_distance_m": None}
    other = {"day": "tirs", "done": False, "disc": "run", "label": "Løb Z2 40 min"}
    kwargs = _base_speech_kwargs(today_session, [today_session, other])
    kwargs.update(block_type=block_type, compliance=compliance, tss_act=100, planned=250)
    return kwargs


@pytest.mark.parametrize("block", ["RACE", "RECOVERY", "TAPER"])
def test_coach_speech_no_tss_share_in_low_load_blocks(block):
    speech, highlight = coach.generate_coach_speech(**_low_load_kwargs(block))
    combined = speech + " " + highlight
    assert "TSS er i hus" not in combined
    assert "procent af ugens TSS" not in combined
    assert "af planlagt TSS" not in combined
    assert "Lavere belastning er meningen" in combined


@pytest.mark.parametrize("compliance", [40, 95])
def test_coach_speech_no_tss_share_regardless_of_compliance(compliance):
    speech, highlight = coach.generate_coach_speech(**_low_load_kwargs("RECOVERY", compliance))
    assert "TSS" not in speech + " " + highlight


def test_coach_speech_keeps_tss_share_in_build():
    speech, highlight = coach.generate_coach_speech(**_low_load_kwargs("BUILD", 40))
    combined = speech + " " + highlight
    assert "100 af 250 TSS er i hus" in combined
    assert "Lavere belastning er meningen" not in combined


def test_coach_is_stale_only_when_regeneration_was_due():
    # ren tal-drift inden for cachen (HRV/søvn/CTL) -> ikke stale
    assert coach.coach_is_stale("a", "b", cache_fresh=True) is False
    # samme kontekst -> aldrig stale
    assert coach.coach_is_stale("a", "a", cache_fresh=False) is False
    # cache brudt (alder eller ny aktivitet/vejning/AF/plan) men ingen ny vurdering -> stale
    assert coach.coach_is_stale("a", "b", cache_fresh=False) is True
    # ingen hash (kontekst fejlede) -> ikke stale
    assert coach.coach_is_stale("a", None, cache_fresh=False) is False
