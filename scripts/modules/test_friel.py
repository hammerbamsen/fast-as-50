# -*- coding: utf-8 -*-
"""Tests for friel.py — mock-planer der rammer hver regel isoleret."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import friel


def mk_plan(days, weeks=None, travel=None, total_weeks=2):
    return {
        "program": {"start": "2026-06-01", "totalWeeks": total_weeks},
        "weeks": weeks or [{"week": w, "blockType": "BUILD", "tssTarget": 300}
                           for w in range(1, total_weeks + 1)],
        "travel": travel or [],
        "athletes": {"kennet": {"days": days}},
    }


def day(d, *workouts, rest=False):
    if rest:
        return {"date": d, "entries": [{"workout": None, "note": "Hvile"}]}
    return {"date": d, "entries": [{"workout": w, "note": ""} for w in workouts]}


RUN = {"name": "Løb Z2 60 min", "type": "Run"}
VO2 = {"name": "Løb VO2 5×3 Z4", "type": "Run"}
BIKE = {"name": "Cykel Z2", "type": "Ride"}


def test_max_runs_flagged():
    days = [day(f"2026-06-0{i}", RUN) for i in range(1, 5)]  # 4 løbedage uge 1
    flags = friel.structural_flags(mk_plan(days))
    assert any(f["rule"] == "max_runs" and f["week"] == 1 and f["level"] == "HARD"
               for f in flags)


def test_three_runs_ok():
    days = [day("2026-06-01", RUN), day("2026-06-03", VO2), day("2026-06-05", RUN),
            day("2026-06-06", BIKE)]
    flags = friel.structural_flags(mk_plan(days))
    assert not any(f["rule"] == "max_runs" for f in flags)


def test_consecutive_runs_flagged():
    days = [day("2026-06-01", RUN), day("2026-06-02", RUN)]
    flags = friel.structural_flags(mk_plan(days))
    assert any(f["rule"] == "consecutive_runs" for f in flags)


def test_vo2_missing_in_build():
    days = [day("2026-06-01", RUN), day("2026-06-03", BIKE)]
    flags = friel.structural_flags(mk_plan(days))
    assert any(f["rule"] == "vo2_missing" and f["week"] == 1 for f in flags)


def test_vo2_present_no_flag():
    days = [day("2026-06-01", VO2), day("2026-06-03", BIKE)]
    flags = friel.structural_flags(mk_plan(days))
    assert not any(f["rule"] == "vo2_missing" and f["week"] == 1 for f in flags)


def test_recovery_missing_after_3_builds():
    weeks = [{"week": w, "blockType": "BUILD", "tssTarget": 300} for w in range(1, 5)]
    days = [day(f"2026-06-{1 + 7*(w-1):02d}", VO2) for w in range(1, 5)]
    flags = friel.structural_flags(mk_plan(days, weeks=weeks, total_weeks=4))
    assert any(f["rule"] == "missing_recovery" and f["week"] == 4 for f in flags)


def test_recovery_resets_streak():
    weeks = [{"week": 1, "blockType": "BUILD", "tssTarget": 300},
             {"week": 2, "blockType": "BUILD", "tssTarget": 300},
             {"week": 3, "blockType": "RECOVERY", "tssTarget": 150},
             {"week": 4, "blockType": "BUILD", "tssTarget": 300}]
    days = [day(f"2026-06-{1 + 7*(w-1):02d}", VO2) for w in range(1, 5)]
    flags = friel.structural_flags(mk_plan(days, weeks=weeks, total_weeks=4))
    assert not any(f["rule"] == "missing_recovery" for f in flags)


def test_tsb_floor_flagged_with_high_tss():
    # Ekstrem TSS-target -> ATL eksploderer -> TSB under -30
    weeks = [{"week": w, "blockType": "BUILD", "tssTarget": 1400} for w in (1, 2)]
    days = [day(f"2026-06-{d:02d}", BIKE) for d in range(1, 15)]
    plan = mk_plan(days, weeks=weeks)
    flags = friel.load_flags(plan, seed_ctl=40, seed_atl=40, seed_date="2026-05-31")
    assert any(f["rule"] == "tsb_floor" and f["level"] == "HARD" for f in flags)


def test_camp_week_uses_lower_floor():
    weeks = [{"week": 1, "blockType": "BUILD", "tssTarget": 800},
             {"week": 2, "blockType": "BUILD", "tssTarget": 800}]
    days = [day(f"2026-06-{d:02d}", BIKE) for d in range(1, 15)]
    travel = [{"name": "Mallorca camp", "start": "2026-06-01", "end": "2026-06-14"}]
    plan = mk_plan(days, weeks=weeks, travel=travel)
    camps = friel._camp_weeks(plan)
    assert camps == {1, 2}


def test_ctl_ramp_hard_and_soft():
    weeks = [{"week": 1, "blockType": "BUILD", "tssTarget": 100},
             {"week": 2, "blockType": "BUILD", "tssTarget": 900}]
    days = [day(f"2026-06-{d:02d}", BIKE) for d in range(1, 15)]
    plan = mk_plan(days, weeks=weeks)
    flags = friel.load_flags(plan, seed_ctl=30, seed_atl=30, seed_date="2026-05-31")
    assert any(f["rule"] == "ctl_ramp" and f["level"] == "HARD" and f["week"] == 2
               for f in flags)


def test_projection_seeds_from_actuals():
    weeks = [{"week": 1, "blockType": "BUILD", "tssTarget": 0},
             {"week": 2, "blockType": "BUILD", "tssTarget": 0}]
    days = [day("2026-06-01", rest=True)]
    plan = mk_plan(days, weeks=weeks)
    proj = friel.project_fitness(plan, seed_ctl=50, seed_atl=60, seed_date="2026-06-01")
    first = proj["2026-06-02"]
    assert first["ctl"] < 50 and first["atl"] < 60  # decay uden TSS
    assert first["tsb"] == round(first["ctl"] - first["atl"], 1)


def test_validate_combines_and_sorts():
    days = [day(f"2026-06-0{i}", RUN) for i in range(1, 5)]
    flags = friel.validate(mk_plan(days), seed_ctl=40, seed_atl=40,
                           seed_date="2026-05-31")
    assert flags == sorted(flags, key=lambda f: (f["week"], f["rule"]))
    assert any(f["rule"] == "max_runs" for f in flags)


def test_vo2_markers_match_real_names():
    bjerg = {"name": "Cykel bjerg-intervaller Z4 Mallorca", "type": "Ride"}
    calobra = {"name": "Cykel Sa Calobra via Puig Major", "type": "Ride"}
    assert friel._is_vo2(bjerg) and friel._is_vo2(calobra)


def test_historic_flag_marking():
    days = [day(f"2026-06-0{i}", RUN) for i in range(1, 5)]
    plan = mk_plan(days)
    plan["athletes"]["kennet"]["actualsThroughWeek"] = 1
    flags = friel.validate(plan)
    assert all(f["historic"] for f in flags if f["week"] == 1)


# ── T2: Taper-protokol ─────────────────────────────────────────────

def mk_taper_plan(tss_by_week, block_by_week, races=None, total_weeks=3):
    weeks = [{"week": w, "blockType": block_by_week[w - 1],
              "tssTarget": tss_by_week[w - 1]} for w in range(1, total_weeks + 1)]
    days = []
    from datetime import date, timedelta
    d0 = date(2026, 6, 1)
    for i in range(total_weeks * 7):
        d = (d0 + timedelta(days=i)).isoformat()
        days.append(day(d, BIKE))  # kun cykel: ingen løbe-flags forstyrrer
    p = mk_plan(days, weeks=weeks, total_weeks=total_weeks)
    p["races"] = races or []
    return p


def test_taper_deep_tsb_not_flagged_at_old_floor():
    # TSB ca. -12 i taper: ville aldrig flage ved -30, må heller ikke ved -15
    p = mk_taper_plan([400, 250, 150], ["BUILD", "TAPER", "TAPER"])
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=52, seed_date="2026-05-31")
    assert not any(f["rule"] == "tsb_floor" and f["week"] in (2, 3) for f in flags)


def test_taper_tsb_floor_minus_15():
    # Meget høj TSS i taper-uge -> TSB dybt negativ -> HARD ved -15-gulvet
    p = mk_taper_plan([400, 900, 150], ["BUILD", "TAPER", "TAPER"])
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=52, seed_date="2026-05-31")
    assert any(f["rule"] == "tsb_floor" and f["week"] == 2 and "(taper)" in f["msg"]
               for f in flags)


def test_taper_negative_ramp_no_flag():
    # Faldende CTL i taper er korrekt — ingen ramp-flags
    p = mk_taper_plan([400, 200, 100], ["BUILD", "TAPER", "RACE"])
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=45, seed_date="2026-05-31")
    assert not any(f["rule"] in ("ctl_ramp", "taper_ctl_rising") and f["week"] in (2, 3)
                   for f in flags)


def test_taper_rising_ctl_flagged():
    # Stigende CTL i taper-uge -> taper_ctl_rising WARN (ikke ctl_ramp)
    p = mk_taper_plan([300, 700, 100], ["BUILD", "TAPER", "RACE"])
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=45, seed_date="2026-05-31")
    assert any(f["rule"] == "taper_ctl_rising" and f["week"] == 2 for f in flags)
    assert not any(f["rule"] == "ctl_ramp" and f["week"] == 2 for f in flags)


def test_race_week_tsb_floor_skipped():
    # Selv absurd TSS i RACE-uge giver ikke tsb_floor (vurderes på race-dag)
    p = mk_taper_plan([400, 200, 900], ["BUILD", "TAPER", "RACE"])
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=45, seed_date="2026-05-31")
    assert not any(f["rule"] == "tsb_floor" and f["week"] == 3 for f in flags)


def test_race_day_low_tsb_flagged():
    # Hård belastning helt frem til race -> TSB < +5 på race-dag -> WARN
    p = mk_taper_plan([400, 400, 400], ["BUILD", "TAPER", "RACE"],
                      races=[{"name": "Testrace", "date": "2026-06-20"}])
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=45, seed_date="2026-05-31")
    assert any(f["rule"] == "race_tsb" and "Testrace" in f["msg"] for f in flags)


def test_race_day_good_tsb_no_flag():
    # Korrekt taper -> TSB i +5..+25 på race-dag -> ingen flags
    p = mk_taper_plan([350, 120, 60], ["BUILD", "TAPER", "RACE"],
                      races=[{"name": "Testrace", "date": "2026-06-20"}])
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=45, seed_date="2026-05-31")
    assert not any(f["rule"] == "race_tsb" for f in flags)


def test_dual_race_both_checked():
    # To A-races 7 dage fra hinanden: hård belastning hele vejen ->
    # BEGGE race-dage skal flages individuelt (ingen dato må slippe forbi)
    p = mk_taper_plan([400, 400, 400, 400], ["BUILD", "TAPER", "TAPER", "RACE"],
                      races=[{"name": "Race A", "date": "2026-06-20"},
                             {"name": "Race B", "date": "2026-06-27"}],
                      total_weeks=4)
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=45, seed_date="2026-05-31")
    msgs = [f["msg"] for f in flags if f["rule"] == "race_tsb"]
    assert any("Race A" in m for m in msgs)
    assert any("Race B" in m for m in msgs)


def test_dual_race_correct_taper_no_flags():
    # Korrekt dobbelt-race-taper: TSB vedligeholdes mellem racene -> ingen flags
    p = mk_taper_plan([350, 120, 60, 60], ["BUILD", "TAPER", "TAPER", "RACE"],
                      races=[{"name": "Race A", "date": "2026-06-20"},
                             {"name": "Race B", "date": "2026-06-27"}],
                      total_weeks=4)
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=45, seed_date="2026-05-31")
    assert not any(f["rule"] == "race_tsb" for f in flags)


def test_backward_compat_missing_blocktype():
    # Uger uden blockType -> hidtidig adfærd (gulv -30, normale ramp-regler)
    p = mk_taper_plan([400, 900, 150], [None, None, None])
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=52, seed_date="2026-05-31")
    hard = [f for f in flags if f["rule"] == "tsb_floor"]
    assert all("-30" in f["msg"] for f in hard) or hard == []
