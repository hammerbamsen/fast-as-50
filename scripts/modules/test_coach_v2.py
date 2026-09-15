# -*- coding: utf-8 -*-
"""Tests for coach v2: prompt-filer, tool-schema, mekanisk validering og
generate_coach_v2 med mocket Anthropic-kald."""
import json
import os
from datetime import date

import pytest

from modules import coach
from modules import coach_context as cc
from modules import coach_validate as cv

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _plan():
    with open(os.path.join(_ROOT, "data", "plan.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _ctx(today=date(2026, 9, 8)):
    data = {
        "week_sessions": [
            {"day": "Man", "label": "Styrke 25 min", "disc": "strength", "done": True, "actual_mins": 22, "actual_tss": 14, "planned_tss": 17},
            {"day": "Tir", "label": "Gang let 60 min", "disc": "hike", "done": False, "today": True, "planned_mins": 60},
            {"day": "Ons", "label": "Svøm 30 min", "disc": "swim", "done": False, "planned_mins": 30},
        ],
        "ctlCurve": [48.0, 50.4], "tsb": -0.7,
        "hrvHistory": [{"date": "2026-09-07", "v": 58.0}, {"date": "2026-09-08", "v": 54.0}],
        "sleepHistory": [{"date": "2026-09-08", "v": 6.4}],
        "weightMovingAvg7": [72.9, 72.5], "fatMovingAvg7": [21.7, 21.6],
        "weightHistory": [{"date": "2026-09-08", "v": 72.3}],
        "af": {"weekDone": 1, "target": 6, "streak": 1},
    }
    return cc.build_context(_plan(), data, today, ctl=50.4, atl=51.1, tsb=-0.7, tss_actual=14)


def _answer(**over):
    a = {
        "oneThing": {"action": "Gå de 60 min i Z1 i dag — ingen løb før lørdag.",
                     "why": "Uge 1 er restitution efter Médoc; søvn 6,4 t i nat."},
        "training": {"text": "Styrke i går: 22 min mod planlagte 25. CTL 50,4 mod ugemål 47 er fint i en RECOVERY-uge.", "refs": [22, 25, 50.4, 47]},
        "body": {"text": "7-dages snit 72,5 kg; cut starter først 21/9. Stabil.", "refs": [72.5]},
        "habits": {"text": "1 af 6 AF-dage. Søvn 6,4 t er under 7.", "refs": [1, 6, 6.4, 7]},
        "bigPicture": "Uge 1 af 51 i Tour des Stations 2027 — restitution efter Médoc, derfor lav belastning.",
        "weekFocus": None,
        "warnings": [],
    }
    a.update(over)
    return a


# ── Prompt-filer ────────────────────────────────────────────────────────────

def test_prompt_files_exist_with_key_sections():
    system = coach.load_prompt("coach_system")
    for key in ("Træner + diætist", "52", "Fast as Fifty", "du-form", "PLAN ≠ FAKTISK",
                "protein ved hvert måltid", "LOW", "RECOVERY", "72", "0,3 kg", "0,5 procentpoint",
                "HOLD CTL", "kvote", "ALDRIG kulhydrat"):
        assert key.lower() in system.lower(), key
    daily = coach.load_prompt("coach_daily")
    assert "{context}" in daily and "oneThing" in daily and "{weekFocusInstruction}" in daily
    sunday = coach.load_prompt("coach_sunday")
    assert "{context}" in sunday and "weekFocus" in sunday and "catalog" in sunday


def test_build_messages_daily_and_sunday():
    ctx = _ctx()
    system, user = coach.build_messages(ctx)
    assert "{context}" not in user and '"program"' in user
    assert "tirsdag" in user and "null (ikke søndag/mandag)" in user
    ctx_sun = _ctx(date(2026, 9, 6))
    system, user = coach.build_messages(ctx_sun)
    assert "Søndagens opgave" in user and '"catalog"' in user
    ctx_mon = _ctx(date(2026, 9, 7))
    _, user = coach.build_messages(ctx_mon)
    assert "max 12 ord" in user and "Dagens opgave" in user


def test_tool_schema_is_sound():
    t = coach.COACH_TOOL
    props = t["input_schema"]["properties"]
    assert set(t["input_schema"]["required"]) == {"oneThing", "training", "body", "habits", "bigPicture", "weekFocus", "warnings"}
    assert props["warnings"]["items"]["properties"]["level"]["enum"] == ["info", "warn", "act"]
    assert props["warnings"]["items"]["properties"]["action"]["properties"]["edit"]["properties"]["action"]["enum"] == ["move", "cancel", "swap_template"]
    json.dumps(t)


# ── numbers_in_text ─────────────────────────────────────────────────────────

def test_numbers_in_text_ignores_dates_times_weeks():
    t = "Uge 36, 2026-09-08 kl. 06:35 — 21/9 starter cuttet. 5/7 AF-dage. 72,5 kg og -0,7 TSB, 1. sep."
    assert cv.numbers_in_text(t) == [72.5, -0.7]
    assert cv.numbers_in_text("Tor 24/9 FTP-test, 3 af 6 AF-dage, −26,5 %, 7-8 timer, 2x/uge") == [3, 6, -26.5, 7, 8]


def test_numbers_in_text_reads_comma_and_dot():
    assert cv.numbers_in_text("CTL 50,4 og 47 mod 21.6 %") == [50.4, 47.0, 21.6]


# ── validate ────────────────────────────────────────────────────────────────

def test_validate_accepts_valid_answer():
    ctx = _ctx()
    ok, errors, cleaned = cv.validate(_answer(), ctx)
    assert ok, errors
    assert cleaned["oneThing"]["action"].startswith("Gå de 60 min")
    assert cleaned["training"]["refs"] == [22.0, 25.0, 50.4, 47.0]
    assert cleaned["warnings"] == []


def test_validate_rejects_invented_number():
    ctx = _ctx()
    a = _answer(training={"text": "CTL er 53,8 og du har kørt 4 pas.", "refs": [53.8]})
    ok, errors, cleaned = cv.validate(a, ctx)
    assert not ok and cleaned is None
    assert any("53,8" in e and "training.text" in e for e in errors)


def test_validate_allows_integer_rounding_and_small_counts():
    ctx = _ctx()
    a = _answer(training={"text": "CTL 50 (afrundet) og 3 pas i ugen — ét er gjort.", "refs": [50]})
    ok, errors, _ = cv.validate(a, ctx)
    assert ok, errors


def test_validate_rejects_tss_status_as_one_thing():
    ctx = _ctx()
    a = _answer(oneThing={"action": "122 procent af ugens TSS er i hus", "why": "godt gået"})
    ok, errors, _ = cv.validate(a, ctx)
    assert not ok and any("TSS-status" in e for e in errors)


def test_validate_drops_warning_action_with_unknown_entry_id():
    ctx = _ctx()
    ctx["week"]["upcoming"] = [{"id": "abc123", "date": "2026-09-10", "name": "Svøm", "disc": "swim"}]
    a = _answer(warnings=[
        {"type": "spacing", "level": "act", "message": "For tæt på næste hårde pas.",
         "action": {"label": "Flyt", "edit": {"action": "move", "entryId": "findes-ikke", "toDate": "2026-09-12"}}},
        {"type": "quota", "level": "warn", "message": "Kvoten er brugt.",
         "action": {"label": "Aflys", "edit": {"action": "cancel", "entryId": "abc123"}}},
        {"type": "info", "level": "critical", "message": "Bare info.", "action": None},
    ])
    ok, errors, cleaned = cv.validate(a, ctx)
    assert ok, errors
    ws = cleaned["warnings"]
    assert ws[0]["level"] == "act" and ws[0]["action"] is None      # ukendt id -> handling fjernet
    assert ws[1]["action"]["edit"] == {"action": "cancel", "entryId": "abc123"}
    assert ws[2]["level"] == "warn"                                  # 'critical' normaliseret
    assert cleaned["validationNotes"] and "findes-ikke" in cleaned["validationNotes"][0]


def test_validate_requires_week_focus_on_sunday_monday():
    ctx = _ctx(date(2026, 9, 7))
    ok, errors, _ = cv.validate(_answer(), ctx, require_week_focus=True)
    assert not ok and any("weekFocus" in e for e in errors)
    ok, errors, cleaned = cv.validate(_answer(weekFocus='"Let uge — gang, svøm og cykel."'), ctx, require_week_focus=True)
    assert ok and cleaned["weekFocus"] == "Let uge — gang, svøm og cykel"


def test_validate_truncates_lengths():
    ctx = _ctx()
    a = _answer(oneThing={"action": "x" * 300, "why": "y" * 300})
    ok, _, cleaned = cv.validate(a, ctx)
    assert ok and len(cleaned["oneThing"]["action"]) == 140 and len(cleaned["oneThing"]["why"]) == 160


def test_merge_warnings_rule_first_action_null_max_three():
    rule = [{"type": "tsb", "level": "critical", "message": "TSB -31"},
            {"type": "hrv", "level": "warn", "message": "HRV lav"}]
    ai = [{"type": "spacing", "level": "act", "message": "For tæt", "action": {"label": "Flyt", "edit": {"action": "move", "entryId": "a"}}},
          {"type": "hrv", "level": "info", "message": "dublet"},
          {"type": "cut", "level": "info", "message": "info"}]
    m = cv.merge_warnings(rule, ai)
    assert len(m) == 3
    assert [w["level"] for w in m] == ["act", "act", "warn"]
    assert m[0]["type"] == "tsb" and m[0]["action"] is None and m[0]["source"] == "rule"
    assert m[1]["type"] == "spacing" and m[1]["action"]["edit"]["entryId"] == "a"
    assert not any(w["message"] == "dublet" for w in m)


# ── generate_coach_v2 med mock ──────────────────────────────────────────────

def _mock_api(monkeypatch, answers):
    calls = []

    def fake(system, user, api_key, timeout=None):
        calls.append({"system": system, "user": user})
        nxt = answers.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return {"stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "coach_output", "input": nxt}]}
    monkeypatch.setattr(coach, "_call_anthropic", fake)
    return calls


def test_generate_coach_v2_valid_answer(monkeypatch):
    calls = _mock_api(monkeypatch, [_answer()])
    ans, info = coach.generate_coach_v2(_ctx(), api_key="sk-ant-test")
    assert ans and ans["oneThing"]["action"].startswith("Gå de 60 min")
    assert info["validationError"] is None and coach.LAST_AI_ERROR is None
    assert "træner + diætist" in calls[0]["system"].lower() and '"ctl":50.4' in calls[0]["user"]


def test_generate_coach_v2_rejects_invented_number_after_feedback(monkeypatch):
    bad = _answer(body={"text": "Vægten er 69,9 kg.", "refs": [69.9]})
    calls = _mock_api(monkeypatch, [bad, bad])
    ans, info = coach.generate_coach_v2(_ctx(), api_key="sk-ant-test")
    assert ans is None and len(calls) == 2
    assert "69,9" in info["validationError"]
    assert coach.LAST_AI_ERROR.startswith("validering:")
    assert "AFVIST AF VALIDERINGEN" in calls[1]["user"] and "69,9" in calls[1]["user"]
    assert calls[0]["user"] == calls[1]["user"].split("\n\nDIT FORRIGE")[0]
    assert info["validationRejected"][0]["body.text"].startswith("Vægten er 69,9")


def test_generate_coach_v2_feedback_rescues_answer(monkeypatch):
    bad = _answer(habits={"text": "AF-dage 43 % af ugen.", "refs": [43]})
    calls = _mock_api(monkeypatch, [bad, _answer()])
    ans, info = coach.generate_coach_v2(_ctx(), api_key="sk-ant-test")
    assert ans is not None and len(calls) == 2
    assert info["validationError"] is None and coach.LAST_AI_ERROR is None
    assert "43" in calls[1]["user"]
    assert info["validationRejected"] and "43" in info["validationRejected"][0]["errors"][0]


def test_generate_coach_v2_retries_once_on_error(monkeypatch):
    calls = _mock_api(monkeypatch, [TimeoutError("timed out"), _answer()])
    ans, _ = coach.generate_coach_v2(_ctx(), api_key="sk-ant-test")
    assert ans is not None and len(calls) == 2


def test_generate_coach_v2_without_key():
    ans, info = coach.generate_coach_v2(_ctx(), api_key="")
    assert ans is None and "ANTHROPIC_API_KEY" in coach.LAST_AI_ERROR


def test_parse_tool_result_truncated():
    with pytest.raises(ValueError):
        coach.parse_tool_result({"stop_reason": "max_tokens", "content": []})


# ── Rendering til gamle felter ──────────────────────────────────────────────

def test_legacy_fields_and_html():
    a = _answer()
    speech, hl = coach.legacy_fields(a)
    assert "{HL}" in speech and speech.startswith("Uge 1 af 51")
    assert hl == a["oneThing"]["action"]
    html = coach.render_assessment_html(a, "Dag 2 af 357 · tirsdag · Uge 1")
    assert 'class="coach-head"' in html and html.count('class="coach-sec"') == 3
    assert "style=" not in html
    assert "Træning &amp; load" in html and "Krop &amp; kost" in html and "Vaner" in html
