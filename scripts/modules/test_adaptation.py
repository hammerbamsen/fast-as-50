# -*- coding: utf-8 -*-
"""Tests for T3 adaptation-modulet. Køres af ci-pytest.yml (X4)."""
from datetime import date, timedelta

from . import adaptation


TODAY = date(2026, 7, 8)   # onsdag, uge 6


def _wo(name, typ, mins=60, desc=""):
    return {"name": name, "type": typ, "moving_time": mins * 60, "description": desc}


def _base_plan(blockType="BUILD", camp=None):
    """14-ugers plan, start mandag 2026-06-01. Uge 6 = 6.-12. juli."""
    start = date(2026, 6, 1)
    weeks = [{"week": w, "start": (start + timedelta(days=(w-1)*7)).isoformat(),
              "blockType": blockType, "ctlTarget": 30 + w, "tssTarget": 300}
             for w in range(1, 15)]
    days = []
    for i in range(98):
        days.append({"date": (start + timedelta(days=i)).isoformat(), "entries": []})
    plan = {"program": {"name": "F50", "start": start.isoformat(), "totalWeeks": 14},
            "weeks": weeks, "travel": camp or [],
            "athletes": {"kennet": {"name": "Kennet", "days": days}}}
    return plan


def _set(plan, iso, entry):
    for d in plan["athletes"]["kennet"]["days"]:
        if d["date"] == iso:
            d["entries"] = [entry]
            return


def _act(iso, typ, mins=60):
    return {"start_date_local": iso + "T07:00:00", "type": typ,
            "moving_time": mins * 60, "icu_training_load": 50}


# ── detect_missed ────────────────────────────────────────────────

def test_completed_session_not_missed():
    plan = _base_plan()
    plan_iso = (TODAY - timedelta(days=2)).isoformat()
    _set(plan, plan_iso, {"id": "e1", "workout": _wo("Løb Z2 45", "Run", 45)})
    acts = [_act(plan_iso, "Run", 45)]
    assert adaptation.detect_missed(plan, acts, TODAY) == []


def test_missing_activity_is_missed():
    plan = _base_plan()
    plan_iso = (TODAY - timedelta(days=2)).isoformat()
    _set(plan, plan_iso, {"id": "e1", "workout": _wo("Løb Z2 45", "Run", 45)})
    missed = adaptation.detect_missed(plan, [], TODAY)
    assert len(missed) == 1 and missed[0]["entry_id"] == "e1"


def test_activity_within_one_day_counts():
    plan = _base_plan()
    plan_iso = (TODAY - timedelta(days=3)).isoformat()
    _set(plan, plan_iso, {"id": "e1", "workout": _wo("Løb", "Run", 45)})
    # aktivitet dagen efter det planlagte
    act_iso = (TODAY - timedelta(days=2)).isoformat()
    assert adaptation.detect_missed(plan, [_act(act_iso, "Run", 45)], TODAY) == []


def test_short_activity_below_ratio_is_missed():
    plan = _base_plan()
    plan_iso = (TODAY - timedelta(days=2)).isoformat()
    _set(plan, plan_iso, {"id": "e1", "workout": _wo("Løb", "Run", 60)})
    # kun 10 min ud af 60 planlagte = under 30 %
    assert len(adaptation.detect_missed(plan, [_act(plan_iso, "Run", 10)], TODAY)) == 1


def test_travel_day_not_counted():
    camp = [{"name": "Mallorca", "start": (TODAY - timedelta(days=3)).isoformat(),
             "end": (TODAY - timedelta(days=1)).isoformat()}]
    plan = _base_plan(camp=camp)
    plan_iso = (TODAY - timedelta(days=2)).isoformat()
    _set(plan, plan_iso, {"id": "e1", "workout": _wo("Løb", "Run", 45)})
    assert adaptation.detect_missed(plan, [], TODAY) == []


def test_today_not_counted():
    plan = _base_plan()
    _set(plan, TODAY.isoformat(), {"id": "e1", "workout": _wo("Løb", "Run", 45)})
    assert adaptation.detect_missed(plan, [], TODAY) == []


def test_activity_used_only_once():
    plan = _base_plan()
    i1 = (TODAY - timedelta(days=2)).isoformat()
    i2 = (TODAY - timedelta(days=3)).isoformat()
    _set(plan, i1, {"id": "e1", "workout": _wo("Løb A", "Run", 45)})
    _set(plan, i2, {"id": "e2", "workout": _wo("Løb B", "Run", 45)})
    # kun én løbe-aktivitet — skal dække kun ét af de to pas
    missed = adaptation.detect_missed(plan, [_act(i1, "Run", 45)], TODAY)
    assert len(missed) == 1


# ── suggest: tærskler ────────────────────────────────────────────

def _missed_days(n, start_offset=2):
    return [{"date": (TODAY - timedelta(days=start_offset + i)).isoformat(),
             "entry_id": f"m{i}", "name": "Løb", "type": "Run"} for i in range(n)]


def test_one_missed_does_not_trigger():
    plan = _base_plan()
    out = adaptation.suggest(plan, _missed_days(1), TODAY)
    assert out["triggered"] is False and out["suggestion"] is None


def test_two_missed_7d_triggers():
    plan = _base_plan()
    hard_iso = (TODAY + timedelta(days=1)).isoformat()
    _set(plan, hard_iso, {"id": "h1", "workout": _wo("Løb VO2 5×3 min", "Run", 60)})
    out = adaptation.suggest(plan, _missed_days(2), TODAY)
    assert out["triggered"] is True and out["suggestion"] is not None
    assert out["suggestion"]["entry_id"] == "h1"


def test_three_missed_10d_triggers():
    plan = _base_plan()
    hard_iso = (TODAY + timedelta(days=1)).isoformat()
    _set(plan, hard_iso, {"id": "h1", "workout": _wo("Cykel 5×3 min Z4", "Ride", 60)})
    # spred 3 missede over 10 dage (kun 1 inden for 7d)
    missed = [{"date": (TODAY - timedelta(days=d)).isoformat(),
               "entry_id": f"m{d}", "name": "x", "type": "Run"} for d in (3, 8, 9)]
    out = adaptation.suggest(plan, missed, TODAY)
    assert out["triggered"] is True


# ── suggest: forslag-logik ───────────────────────────────────────

def test_low_readiness_suggests_rest():
    plan = _base_plan()
    hard_iso = (TODAY + timedelta(days=1)).isoformat()
    _set(plan, hard_iso, {"id": "h1", "workout": _wo("Løb VO2 5×3 min", "Run", 60)})
    out = adaptation.suggest(plan, _missed_days(2), TODAY, readiness="LOW")
    assert out["suggestion"]["suggested_action"] == "cancel"


def test_normal_readiness_suggests_z2_swap():
    plan = _base_plan()
    hard_iso = (TODAY + timedelta(days=1)).isoformat()
    _set(plan, hard_iso, {"id": "h1", "workout": _wo("Cykel 5×3 min Z4", "Ride", 60)})
    out = adaptation.suggest(plan, _missed_days(2), TODAY, readiness="NORMAL")
    assert out["suggestion"]["suggested_action"] == "swap_template"
    assert out["suggestion"]["params"]["template_id"] == "cykel-z2-60"


def test_vo2_note_present_for_vo2_target():
    plan = _base_plan()
    hard_iso = (TODAY + timedelta(days=1)).isoformat()
    _set(plan, hard_iso, {"id": "h1", "workout": _wo("Løb VO2 5×3 min", "Run", 60)})
    out = adaptation.suggest(plan, _missed_days(2), TODAY, readiness="NORMAL")
    assert "vo2_note" in out["suggestion"]


# ── suggest: fase-guard ──────────────────────────────────────────

def test_recovery_week_no_suggestion():
    plan = _base_plan(blockType="RECOVERY")
    hard_iso = (TODAY + timedelta(days=1)).isoformat()
    _set(plan, hard_iso, {"id": "h1", "workout": _wo("Løb VO2 5×3 min", "Run", 60)})
    out = adaptation.suggest(plan, _missed_days(2), TODAY)
    assert out["triggered"] is True
    assert out["suggestion"] is None
    assert out["phase_guard"] is not None


def test_taper_week_no_suggestion():
    plan = _base_plan(blockType="TAPER")
    out = adaptation.suggest(plan, _missed_days(3), TODAY)
    assert out["suggestion"] is None and out["phase_guard"] is not None


def test_no_hard_session_ahead_no_suggestion():
    plan = _base_plan()   # ingen hårde pas sat frem i tid
    out = adaptation.suggest(plan, _missed_days(2), TODAY)
    assert out["triggered"] is True and out["suggestion"] is None


# ── signature (hash-guard-input) ────────────────────────────────

def test_signature_stable_and_changes():
    plan = _base_plan()
    hard_iso = (TODAY + timedelta(days=1)).isoformat()
    _set(plan, hard_iso, {"id": "h1", "workout": _wo("Løb VO2 5×3 min", "Run", 60)})
    a = adaptation.suggest(plan, _missed_days(2), TODAY)
    b = adaptation.suggest(plan, _missed_days(2), TODAY)
    assert adaptation.signature(a) == adaptation.signature(b)
    c = adaptation.suggest(plan, _missed_days(3), TODAY)
    assert adaptation.signature(a) != adaptation.signature(c)


# ── robusthed: malformed plan må ikke crashe ────────────────────

def test_malformed_plan_does_not_crash():
    """Tom/delvis plan (fx korrupt eller under samtidig skrivning) degraderer pænt."""
    for bad in [{}, {"athletes": {}}, {"athletes": {"kennet": {}}},
                {"athletes": {"kennet": {"days": []}}}]:
        out = adaptation.compute_adaptation(bad, [], TODAY, readiness="HIGH")
        assert out["triggered"] is False
        assert out["suggestion"] is None


def test_extreme_all_missed_gives_single_suggestion():
    """2 ugers total inaktivitet giver ÉT forslag, ikke spam."""
    plan = _base_plan()
    hard_iso = (TODAY + timedelta(days=1)).isoformat()
    _set(plan, hard_iso, {"id": "h1", "workout": _wo("Løb VO2 5×3 min Z4", "Run", 60)})
    # 10 missede pas
    missed = [{"date": (TODAY - timedelta(days=d)).isoformat(),
               "entry_id": f"m{d}", "name": "x", "type": "Run"} for d in range(1, 11)]
    out = adaptation.suggest(plan, missed, TODAY, readiness="LOW")
    assert out["triggered"] is True
    # Præcis ét forslag (eller guard) — aldrig en liste
    assert out["suggestion"] is None or isinstance(out["suggestion"], dict)
