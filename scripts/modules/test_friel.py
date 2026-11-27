# -*- coding: utf-8 -*-
"""Tests for friel.py — mock-planer der rammer hver regel isoleret."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from datetime import date, timedelta
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


# ── T1: Wellness-readiness-integration ─────────────────────────────

def test_readiness_band_low_on_hrv_drop():
    # HRV 15% under 7d-snit -> LOW
    assert friel.readiness_band(51.0, 60.0, 7.5) == "LOW"


def test_readiness_band_low_on_short_sleep():
    assert friel.readiness_band(60.0, 60.0, 5.5) == "LOW"


def test_readiness_band_high_when_recovered():
    # HRV >= snit OG søvn >= 7t -> HIGH
    assert friel.readiness_band(62.0, 60.0, 7.5) == "HIGH"


def test_readiness_band_normal_and_missing_data():
    assert friel.readiness_band(58.0, 60.0, 7.5) == "NORMAL"   # HRV lidt lav, søvn god
    assert friel.readiness_band(None, None, None) == "NORMAL"  # intet signal


def test_readiness_none_is_backward_compatible():
    # Uden readiness: nøjagtig samme flags som før (gulv -30)
    weeks = [{"week": w, "blockType": "BUILD", "tssTarget": 700} for w in (1, 2)]
    days = [day(f"2026-06-{d:02d}", BIKE) for d in range(1, 15)]
    p = mk_plan(days, weeks=weeks)
    base = friel.load_flags(p, seed_ctl=40, seed_atl=40, seed_date="2026-05-31")
    with_none = friel.load_flags(p, seed_ctl=40, seed_atl=40, seed_date="2026-05-31",
                                 readiness=None, current_week=1)
    assert base == with_none


def test_readiness_low_tightens_current_week_floor():
    # TSB lander ml. -25 og -30 -> flager KUN når LOW (gulv -25), ikke ved NORMAL
    weeks = [{"week": w, "blockType": "BUILD", "tssTarget": 640} for w in (1, 2)]
    days = [day(f"2026-06-{d:02d}", BIKE) for d in range(1, 15)]
    p = mk_plan(days, weeks=weeks)
    kw = dict(seed_ctl=40, seed_atl=40, seed_date="2026-05-31")
    normal = friel.load_flags(p, **kw)  # gulv -30
    low = friel.load_flags(p, readiness="LOW", current_week=1, **kw)  # gulv -25
    # Find worst tsb i uge 1 for at sikre testen rammer vinduet
    proj = friel.project_fitness(p, 40, 40, "2026-05-31")
    worst1 = min(v["tsb"] for d, v in proj.items() if friel._week_no(d, __import__("datetime").date(2026, 6, 1)) == 1)
    assert -30 <= worst1 < -25, f"testforudsætning: worst uge1 TSB={worst1}"
    assert not any(f["rule"] == "tsb_floor" and f["week"] == 1 for f in normal)
    assert any(f["rule"] == "tsb_floor" and f["week"] == 1
               and "readiness low" in f["msg"] for f in low)


def test_readiness_low_adds_advisory_warn():
    weeks = [{"week": w, "blockType": "BUILD", "tssTarget": 300} for w in (1, 2)]
    days = [day(f"2026-06-{d:02d}", BIKE) for d in range(1, 15)]
    p = mk_plan(days, weeks=weeks)
    flags = friel.load_flags(p, seed_ctl=45, seed_atl=45, seed_date="2026-05-31",
                             readiness="LOW", current_week=1)
    assert any(f["rule"] == "low_readiness" and f["week"] == 1
               and f["level"] == "WARN" for f in flags)


def test_readiness_high_loosens_but_not_below_camp():
    # HIGH sænker normalt gulv til -32, men camp-gulv (-35) er allerede dybere
    weeks = [{"week": 1, "blockType": "BUILD", "tssTarget": 800},
             {"week": 2, "blockType": "BUILD", "tssTarget": 800}]
    days = [day(f"2026-06-{d:02d}", BIKE) for d in range(1, 15)]
    travel = [{"name": "Mallorca camp", "start": "2026-06-01", "end": "2026-06-14"}]
    p = mk_plan(days, weeks=weeks, travel=travel)
    high = friel.load_flags(p, seed_ctl=40, seed_atl=40, seed_date="2026-05-31",
                            readiness="HIGH", current_week=1)
    # camp-uge 1 med HIGH: gulvet må IKKE hæves over -35 (stadig -35 i msg hvis flag)
    for f in high:
        if f["rule"] == "tsb_floor" and f["week"] == 1:
            assert "-35" in f["msg"] or "camp" in f["msg"]


def test_readiness_does_not_touch_non_current_week():
    weeks = [{"week": w, "blockType": "BUILD", "tssTarget": 560} for w in (1, 2)]
    days = [day(f"2026-06-{d:02d}", BIKE) for d in range(1, 15)]
    p = mk_plan(days, weeks=weeks)
    # LOW gælder current_week=1; uge 2 skal have uændret gulv (-30)
    low = friel.load_flags(p, seed_ctl=40, seed_atl=40, seed_date="2026-05-31",
                           readiness="LOW", current_week=1)
    for f in low:
        if f["rule"] == "tsb_floor" and f["week"] == 2:
            assert "readiness" not in f["msg"]


def test_validate_passes_readiness_through():
    days = [day("2026-06-01", VO2), day("2026-06-03", BIKE)]
    p = mk_plan(days)
    flags = friel.validate(p, seed_ctl=45, seed_atl=45, seed_date="2026-05-31",
                           readiness="LOW", current_week=1)
    assert any(f["rule"] == "low_readiness" for f in flags)


# ── Valgfrie pas (optional) ──────────────────────────────────────────────────

def opt_day(d, *workouts):
    """Dag hvor alle pas er markeret valgfrie."""
    return {"date": d, "entries": [{"workout": w, "note": "", "optional": True}
                                   for w in workouts]}


def _proj_end(plan):
    p = friel.project_fitness(plan, seed_ctl=40, seed_atl=40,
                              seed_date="2026-05-31")
    return p[max(p)]["ctl"]


def test_optional_day_lowers_projection():
    """Valgfri dag => uge-TSS falder med dagens andel (konservativt scenarie)."""
    base_days = [day("2026-06-01", BIKE), day("2026-06-03", BIKE),
                 day("2026-06-05", BIKE), day("2026-06-06", BIKE)]
    opt_days = [day("2026-06-01", BIKE), day("2026-06-03", BIKE),
                day("2026-06-05", BIKE), opt_day("2026-06-06", BIKE)]
    assert _proj_end(mk_plan(opt_days)) < _proj_end(mk_plan(base_days))


def test_optional_day_does_not_redistribute_load():
    """Nævneren er uændret: de obligatoriske dage bliver IKKE tungere.

    Kontrol: fjernes den valgfrie dag helt fra planen, fordeles samme uge-TSS
    paa 3 dage og projektionen bliver hoejere end med flaget.
    """
    opt_days = [day("2026-06-01", BIKE), day("2026-06-03", BIKE),
                day("2026-06-05", BIKE), opt_day("2026-06-06", BIKE)]
    dropped = [day("2026-06-01", BIKE), day("2026-06-03", BIKE),
               day("2026-06-05", BIKE)]
    assert _proj_end(mk_plan(opt_days)) < _proj_end(mk_plan(dropped))


def test_optional_run_still_counts_in_structural_rules():
    """Worst case: et valgfrit loeb KAN koeres — max_runs skal stadig fange det."""
    days = [day("2026-06-01", RUN), day("2026-06-03", RUN),
            day("2026-06-05", RUN), opt_day("2026-06-07", RUN)]
    flags = friel.structural_flags(mk_plan(days))
    assert any(f["rule"] == "max_runs" and f["week"] == 1 for f in flags)


def test_plan_without_optional_flag_unchanged():
    """Bagudkompatibilitet: planer uden 'optional' projekterer som foer."""
    days = [day("2026-06-01", BIKE), day("2026-06-03", BIKE)]
    p = friel.project_fitness(mk_plan(days), seed_ctl=40, seed_atl=40,
                              seed_date="2026-05-31")
    assert p["2026-06-01"]["ctl"] > 40.0


# ── Løbsdage og taper/race-uger (løbe-regler undtages) ──────────────────────

def mk_race_plan(block_by_week, days, races=None):
    weeks = [{"week": i + 1, "blockType": b, "tssTarget": 200}
             for i, b in enumerate(block_by_week)]
    p = mk_plan(days, weeks=weeks, total_weeks=len(block_by_week))
    p["races"] = races or []
    return p


def test_race_day_not_counted_as_run():
    """Selve løbet er ikke et træningspas — det må ikke tælle i max_runs."""
    days = [day("2026-06-01", RUN), day("2026-06-03", RUN),
            day("2026-06-05", RUN), day("2026-06-07", RUN)]
    races = [{"name": "Test", "date": "2026-06-07", "priority": "A"}]
    p = mk_race_plan(["BUILD"], days, races)
    assert not any(f["rule"] == "max_runs" for f in friel.structural_flags(p))
    # uden races-listen udløses reglen stadig
    p2 = mk_race_plan(["BUILD"], days, [])
    assert any(f["rule"] == "max_runs" for f in friel.structural_flags(p2))


def test_taper_week_exempt_from_run_rules():
    days = [day("2026-06-01", RUN), day("2026-06-02", RUN),
            day("2026-06-03", RUN), day("2026-06-04", RUN)]
    p = mk_race_plan(["TAPER"], days)
    flags = friel.structural_flags(p)
    assert not any(f["rule"] in ("max_runs", "consecutive_runs") for f in flags)


def test_race_week_exempt_from_run_rules():
    days = [day("2026-06-01", RUN), day("2026-06-02", RUN),
            day("2026-06-03", RUN), day("2026-06-04", RUN)]
    p = mk_race_plan(["RACE"], days)
    flags = friel.structural_flags(p)
    assert not any(f["rule"] in ("max_runs", "consecutive_runs") for f in flags)


def test_build_week_still_flagged():
    """Undtagelsen må ikke lække ud i build-uger."""
    days = [day("2026-06-01", RUN), day("2026-06-02", RUN),
            day("2026-06-03", RUN), day("2026-06-04", RUN)]
    p = mk_race_plan(["BUILD"], days)
    flags = friel.structural_flags(p)
    assert any(f["rule"] == "max_runs" for f in flags)
    assert any(f["rule"] == "consecutive_runs" for f in flags)


def test_missing_races_key_is_safe():
    days = [day("2026-06-01", RUN), day("2026-06-02", RUN)]
    p = mk_plan(days)          # ingen 'races'-nøgle overhovedet
    assert any(f["rule"] == "consecutive_runs" for f in friel.structural_flags(p))


# ── Program-drevet validering (3/9-2026) ────────────────────────────────────

def test_phase_normalises_new_block_types():
    wm = {w: {"blockType": bt} for w, bt in enumerate(
        ["BASE", "BASE+", "TRANSITION", "SPECIFIK", "SPECIFIK+", "STELVIO", "PEAK",
         "BUILD", "BUILD+", "CAMP", "RECOVERY", "TAPER", "RACE", None], start=1)}
    exp = ["BASE", "BASE", "BASE", "BUILD", "BUILD", "BUILD", "BUILD",
           "BUILD", "BUILD", "BUILD", "RECOVERY", "TAPER", "RACE", ""]
    assert [friel._phase(wm, w) for w in range(1, 15)] == exp


def test_validate_against_real_plan_after_program_switch():
    """Mod den rigtige plan.json: efter 7/9-2026 valideres mod tds-2027, foer mod
    medoc-2026, og historik-markeringen foelger det program feltet peger paa.

    Laaser ikke HVILKET program markoeren peger paa: det kan aendres via et
    forslag (set_actuals, 27/11-2026), og testen blev roed da det skete."""
    import json
    import programs as P
    plan = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "data", "plan.json"),
                          encoding="utf-8"))
    for seed_date, today in (("2026-09-07", "2026-10-01"), ("2026-07-07", "2026-07-07")):
        prog = P.active_program(plan, "kennet", today=today)
        actuals = P.actuals_through_week(plan, "kennet", prog)
        flags = friel.validate(plan, seed_ctl=45.0, seed_atl=40.0,
                               seed_date=seed_date, today=today)
        assert all(1 <= f["week"] <= prog["totalWeeks"] for f in flags)
        assert all(f["historic"] == (f["week"] <= actuals) for f in flags)


def test_vo2_missing_ignores_unplanned_weeks():
    """Build-uger uden en eneste dag i dagslisten er ikke planlagt endnu — intet flag."""
    weeks = [{"week": w, "blockType": "BUILD", "tssTarget": 300} for w in (1, 2)]
    days = [day("2026-06-01", RUN)]
    flags = friel.structural_flags(mk_plan(days, weeks=weeks))
    assert any(f["rule"] == "vo2_missing" and f["week"] == 1 for f in flags)
    assert not any(f["rule"] == "vo2_missing" and f["week"] == 2 for f in flags)


# -- Friels 2. udgave: regel 1, 2, 3 og 5 (27/11-2026) ------------------------

def _e2_plan(days, block="BUILD", weeks=3):
    """Minimal plan til edition2_flags. Mandag 4/1-2027 er uge 1."""
    return {
        "programs": {"p": {"id": "p", "start": "2027-01-04", "end": "2027-01-31",
                           "athletes": ["kennet"],
                           "totalWeeks": weeks, "weeks": [
            {"week": w, "start": (date(2027, 1, 4) + timedelta(weeks=w - 1)).isoformat(),
             "blockType": block, "ctlTarget": 50} for w in range(1, weeks + 1)]}},
        "athletes": {"kennet": {"days": days}},
    }


def _e2_day(d, *entries):
    return {"date": d, "entries": list(entries)}


def _lib(wid, wtype="Ride"):
    return {"id": wid, "libraryId": wid, "workout": {"type": wtype, "name": wid}}


def _named(name, wtype="Ride"):
    return {"id": name[:6], "workout": {"type": wtype, "name": name}}


def _rules(flags):
    from collections import Counter
    return dict(Counter(f["rule"] for f in flags))


def test_entry_load_laeser_biblioteket_foerst_saa_navnet():
    assert friel.entry_load(_lib("vo2_4x4")) == "haard"
    assert friel.entry_load(_lib("z2_rolig_60")) == "let"
    # uden libraryId: navnet afgoer
    assert friel.entry_load(_named("Cykel Z2 3 t Mallorca")) == "let"
    assert friel.entry_load(_named("Bjerg VO2 4x4 Puig Major")) == "haard"
    assert friel.entry_load(_named("Løb tærskel 3x10", "Run")) == "haard"
    assert friel.entry_load(_named("Gravel 2 t")) == "moderat"
    # styrke, svoem og vandring taeller ikke med (CLAUDE.md regel 4)
    assert friel.entry_load(_named("Styrke A", "WeightTraining")) is None
    assert friel.entry_load(_named("Svøm 1500m", "Swim")) is None
    assert friel.entry_load({"id": "x", "workout": None}) is None


def test_regel1_max_to_haarde_dage_paa_tvaers_af_discipliner():
    """Hullet reglen lukker: bike_library.check_week() taeller kun cykelpas."""
    days = [_e2_day("2027-01-04", _lib("vo2_4x4")),
            _e2_day("2027-01-06", _named("Løb tærskel 3x10", "Run")),
            _e2_day("2027-01-08", _lib("tae_2x20")),
            _e2_day("2027-01-09", _named("Cykel Z2 2 t")),
            _e2_day("2027-01-10", _named("Cykel Z2 3 t"))]
    fl = friel.edition2_flags(_e2_plan(days), today="2027-01-04")
    assert _rules(fl).get("hard_per_week") == 1
    msg = next(f["msg"] for f in fl if f["rule"] == "hard_per_week")
    assert "3 hårde dage" in msg and "alle discipliner" in msg
    # to haarde er i orden
    days2 = [d for d in days if d["date"] != "2027-01-08"]
    assert "hard_per_week" not in _rules(friel.edition2_flags(_e2_plan(days2), today="2027-01-04"))


def test_regel2_afstand_48_timer_og_72_mellem_to_z5():
    # to haarde med 48 t imellem: ok
    ok = [_e2_day("2027-01-04", _lib("tae_2x20")), _e2_day("2027-01-06", _lib("tae_3x12"))]
    assert "hard_spacing" not in _rules(friel.edition2_flags(_e2_plan(ok), today="2027-01-04"))
    # 24 t imellem: flag
    taet = [_e2_day("2027-01-04", _lib("tae_2x20")), _e2_day("2027-01-05", _lib("tae_3x12"))]
    fl = friel.edition2_flags(_e2_plan(taet), today="2027-01-04")
    assert _rules(fl).get("hard_spacing") == 1
    assert "kræver 48 t" in next(f["msg"] for f in fl if f["rule"] == "hard_spacing")
    # to Z5-pas med 48 t imellem: kraever 72
    z5 = [_e2_day("2027-01-04", _lib("vo2_4x4")), _e2_day("2027-01-06", _lib("vo2_5x3"))]
    fl = friel.edition2_flags(_e2_plan(z5), today="2027-01-04")
    assert _rules(fl).get("hard_spacing") == 1
    assert "begge Z5" in next(f["msg"] for f in fl if f["rule"] == "hard_spacing")
    # samme to Z5-pas med 72 t: ok
    z5ok = [_e2_day("2027-01-04", _lib("vo2_4x4")), _e2_day("2027-01-07", _lib("vo2_5x3"))]
    assert "hard_spacing" not in _rules(friel.edition2_flags(_e2_plan(z5ok), today="2027-01-04"))


def test_regel3_mindst_tre_lette_dage_i_en_fuldt_planlagt_uge():
    # 2 haarde + 4 moderate + 1 let = kun 1 let dag
    haard = [_e2_day("2027-01-04", _lib("vo2_4x4")), _e2_day("2027-01-07", _lib("tae_2x20"))]
    moderat = [_e2_day(d, _named("Gravel 2 t")) for d in
               ("2027-01-05", "2027-01-06", "2027-01-08", "2027-01-09")]
    let = [_e2_day("2027-01-10", _named("Cykel Z2 rolig 1 t"))]
    fl = friel.edition2_flags(_e2_plan(haard + moderat + let), today="2027-01-04")
    assert _rules(fl).get("easy_days_min") == 1
    assert "Kun 1 lette dage" in next(f["msg"] for f in fl if f["rule"] == "easy_days_min")
    # samme uge med 3 lette dage i stedet: ingen flag
    ok = haard + moderat[:2] + [_e2_day(d, _named("Cykel Z2 rolig 1 t")) for d in
                                ("2027-01-08", "2027-01-09", "2027-01-10")]
    assert "easy_days_min" not in _rules(friel.edition2_flags(_e2_plan(ok), today="2027-01-04"))


def test_regel3_flagger_ikke_en_delvist_planlagt_uge():
    """Uger med under 7 dage i dagslisten er ikke faerdigplanlagte."""
    days = [_e2_day("2027-01-04", _lib("vo2_4x4")), _e2_day("2027-01-07", _lib("tae_2x20"))]
    assert "easy_days_min" not in _rules(friel.edition2_flags(_e2_plan(days), today="2027-01-04"))


def test_regel5_loft_for_z5_tid_i_ett_pas():
    assert round(friel.planned_z5_min(_lib("vo2_ronnestad_3015"))) == 20
    assert round(friel.planned_z5_min(_lib("vo2_10x1"))) == 10
    assert friel.planned_z5_min(_named("Cykel Z2 2 t")) == 0      # udendoers: ingen steps
    fl = friel.edition2_flags(_e2_plan([_e2_day("2027-01-04", _lib("vo2_ronnestad_3015"))]),
                              today="2027-01-04")
    assert _rules(fl).get("z5_per_session") == 1
    assert "20 min Z5 i ét pas" in next(f["msg"] for f in fl if f["rule"] == "z5_per_session")
    # 10 min er under loftet
    fl2 = friel.edition2_flags(_e2_plan([_e2_day("2027-01-04", _lib("vo2_10x1"))]),
                               today="2027-01-04")
    assert "z5_per_session" not in _rules(fl2)


def test_regel4_rr_efter_to_belastningsuger_og_camp_taeller_med():
    plan = _e2_plan([_e2_day("2027-01-04", _lib("z2_rolig_60"))], block="BUILD", weeks=3)
    fl = friel.structural_flags(plan, today="2027-01-04")
    rec = [f for f in fl if f["rule"] == "missing_recovery"]
    assert len(rec) == 1 and rec[0]["week"] == 3     # tredje belastningsuge
    assert "max 2 + 5 dage" in rec[0]["msg"]
    # CAMP taeller som belastning — foer saa reglen kun BUILD
    plan["programs"]["p"]["weeks"][2]["blockType"] = "CAMP"
    assert any(f["rule"] == "missing_recovery"
               for f in friel.structural_flags(plan, today="2027-01-04"))
    # en RECOVERY-uge nulstiller
    plan["programs"]["p"]["weeks"][1]["blockType"] = "RECOVERY"
    assert not any(f["rule"] == "missing_recovery"
                   for f in friel.structural_flags(plan, today="2027-01-04"))


def test_taper_og_raceuger_er_fritaget():
    days = [_e2_day(d, _lib("vo2_4x4")) for d in ("2027-01-04", "2027-01-05", "2027-01-06")]
    plan = _e2_plan(days, block="TAPER")
    fl = friel.edition2_flags(plan, today="2027-01-04")
    assert "hard_per_week" not in _rules(fl) and "hard_spacing" not in _rules(fl)
