# -*- coding: utf-8 -*-
"""
Friel-validator — Fast as Fifty.
Genanvendeligt modul: bruges af build_workouts.py (fase 1) og som
server-side gate for plan-redigering (fase 3).

Regler (jf. PROJECT_KICKOFF.md):
  - TSB-gulv -30 (-35 i camp-uger)
  - CTL-ramp max 8/uge (blødt loft 5)
  - Max 3 løb/uge
  - 1x VO2-stimulus pr. build-uge
  - Recovery-uge efter 3-ugers blok
  - Undgå fortløbende løbedage

Input er plan.json-strukturen (dict). Output er liste af flags:
  {"week": int, "rule": str, "level": "WARN"|"HARD", "msg": str}
Reset-års-prioritet: konsistens og løbefrekvens vægtes hårdest —
løbe-regler er HARD, ramp/TSB er HARD ved brud på hårdt loft, WARN ved blødt.
"""
from datetime import date, timedelta

CTL_TC = 42.0   # dage, Coggan/Friel standard
ATL_TC = 7.0

TSB_FLOOR = -30
TSB_FLOOR_CAMP = -35
TSB_FLOOR_TAPER = -15      # taper: TSB skal op — dybt minus er fejl-taper
RACE_TSB_MIN = 5           # Friel: TSB +5..+15 på A-race-dag
RACE_TSB_MAX = 25          # over +25 = detrænet/overtaper
TAPER_RAMP_RISE_WARN = 2.0 # CTL må ikke STIGE i taper/race-uger
RAMP_HARD = 8.0
RAMP_SOFT = 5.0
MAX_RUNS_PER_WEEK = 3


def _phase(weeks_meta, w):
    """Normaliseret fase for uge w. Ukendt/manglende blockType -> ''
    (= hidtidig adfærd, bagudkompatibelt)."""
    bt = ((weeks_meta.get(w) or {}).get("blockType") or "").upper()
    if bt.startswith("BUILD"):
        return "BUILD"
    if bt in ("RECOVERY", "TAPER", "RACE"):
        return bt
    return ""

VO2_MARKERS = ("vo2", "5×3", "4×5", "6×3", "5x3", "4x5", "6x3",
               "bjerg z4", "bjerg-intervaller", "sa calobra")


def _is_run(wo):
    return bool(wo) and wo.get("type") == "Run"


def _is_vo2(wo):
    if not wo:
        return False
    name = (wo.get("name") or "").lower()
    return any(m in name for m in VO2_MARKERS)


def _week_no(d_iso, plan_start):
    return (date.fromisoformat(d_iso) - plan_start).days // 7 + 1


def _camp_weeks(plan):
    """Uger med rejse-ophold markeret som camp (Mallorca) — TSB-gulv -35."""
    camps = set()
    plan_start = date.fromisoformat(plan["program"]["start"])
    for t in plan.get("travel", []):
        name = (t.get("name") or t.get("label") or "").lower()
        if "mallorca" not in name:
            continue
        try:
            s = date.fromisoformat(t["start"])
            e = date.fromisoformat(t.get("end", t["start"]))
        except (KeyError, ValueError):
            continue
        d = s
        while d <= e:
            w = (d - plan_start).days // 7 + 1
            if 1 <= w <= plan["program"]["totalWeeks"]:
                camps.add(w)
            d += timedelta(days=1)
    return camps


def structural_flags(plan, athlete="kennet"):
    """Regler der kun kræver dagslisten: løb/uge, fortløbende løb, VO2, recovery-placering."""
    flags = []
    plan_start = date.fromisoformat(plan["program"]["start"])
    days = plan["athletes"][athlete]["days"]
    weeks_meta = {w["week"]: w for w in plan["weeks"]}
    total_weeks = plan["program"]["totalWeeks"]

    runs_per_week = {w: 0 for w in range(1, total_weeks + 1)}
    vo2_per_week = {w: 0 for w in range(1, total_weeks + 1)}
    run_dates = []

    for d in days:
        w = _week_no(d["date"], plan_start)
        if not 1 <= w <= total_weeks:
            continue
        day_has_run = False
        for e in d["entries"]:
            wo = e.get("workout")
            if _is_run(wo):
                day_has_run = True
            if _is_vo2(wo):
                vo2_per_week[w] += 1
        if day_has_run:
            runs_per_week[w] += 1
            run_dates.append(date.fromisoformat(d["date"]))

    # Max 3 løb/uge — HARD (reset-år: beskyt knæ/fascia)
    for w, n in runs_per_week.items():
        if n > MAX_RUNS_PER_WEEK:
            flags.append({"week": w, "rule": "max_runs", "level": "HARD",
                          "msg": f"{n} løbedage i uge {w} (max {MAX_RUNS_PER_WEEK})"})

    # Fortløbende løbedage — HARD
    run_dates.sort()
    for a, b in zip(run_dates, run_dates[1:]):
        if (b - a).days == 1:
            w = _week_no(b.isoformat(), plan_start)
            flags.append({"week": w, "rule": "consecutive_runs", "level": "HARD",
                          "msg": f"Fortløbende løbedage {a.isoformat()} + {b.isoformat()}"})

    # VO2 1x pr. build-uge — WARN (0 eller >1)
    for w in range(1, total_weeks + 1):
        bt = (weeks_meta.get(w, {}).get("blockType") or "").upper()
        if bt.startswith("BUILD"):
            if vo2_per_week[w] == 0:
                flags.append({"week": w, "rule": "vo2_missing", "level": "WARN",
                              "msg": f"Ingen VO2-stimulus i build-uge {w}"})
            elif vo2_per_week[w] > 1:
                flags.append({"week": w, "rule": "vo2_excess", "level": "WARN",
                              "msg": f"{vo2_per_week[w]} VO2-pas i uge {w} (plan: 1)"})

    # Recovery efter max 3 build-uger i træk — WARN
    streak = 0
    for w in range(1, total_weeks + 1):
        bt = (weeks_meta.get(w, {}).get("blockType") or "").upper()
        if bt.startswith("BUILD"):
            streak += 1
            if streak > 3:
                flags.append({"week": w, "rule": "missing_recovery", "level": "WARN",
                              "msg": f"{streak}. build-uge i træk uden recovery (uge {w})"})
        else:
            streak = 0

    return flags


def project_fitness(plan, seed_ctl, seed_atl, seed_date):
    """
    CTL/ATL/TSB-projektion pr. dag ud fra ugentlige TSS-targets (jævnt fordelt
    på træningsdage). Seedet med FAKTISK Intervals-fitness — ikke lærebogsstart.
    Returnerer {date_iso: {"ctl":…, "atl":…, "tsb":…}} fra seed-dato til planslut.
    """
    plan_start = date.fromisoformat(plan["program"]["start"])
    total_weeks = plan["program"]["totalWeeks"]
    weeks_meta = {w["week"]: w for w in plan["weeks"]}
    days = plan["athletes"]["kennet"]["days"]

    training_days = {}   # week -> antal dage med workout
    day_has_wo = {}
    for d in days:
        w = _week_no(d["date"], plan_start)
        has = any(e.get("workout") for e in d["entries"])
        day_has_wo[d["date"]] = has
        if has:
            training_days[w] = training_days.get(w, 0) + 1

    out = {}
    ctl, atl = float(seed_ctl), float(seed_atl)
    d = date.fromisoformat(seed_date) + timedelta(days=1)
    end = plan_start + timedelta(weeks=total_weeks)
    while d < end:
        w = (d - plan_start).days // 7 + 1
        tss_week = weeks_meta.get(w, {}).get("tssTarget") or 0
        n = training_days.get(w, 0)
        tss = (tss_week / n) if (n and day_has_wo.get(d.isoformat())) else 0.0
        ctl += (tss - ctl) / CTL_TC
        atl += (tss - atl) / ATL_TC
        out[d.isoformat()] = {"ctl": round(ctl, 1), "atl": round(atl, 1),
                              "tsb": round(ctl - atl, 1)}
        d += timedelta(days=1)
    return out


def load_flags(plan, seed_ctl, seed_atl, seed_date):
    """Belastningsregler: TSB-gulv og CTL-ramp, på projekteret fitness."""
    flags = []
    plan_start = date.fromisoformat(plan["program"]["start"])
    total_weeks = plan["program"]["totalWeeks"]
    weeks_meta = {w["week"]: w for w in plan["weeks"]}
    camps = _camp_weeks(plan)
    proj = project_fitness(plan, seed_ctl, seed_atl, seed_date)

    worst_tsb = {}
    week_end_ctl = {}
    for d_iso, v in proj.items():
        w = _week_no(d_iso, plan_start)
        if not 1 <= w <= total_weeks:
            continue
        if w not in worst_tsb or v["tsb"] < worst_tsb[w]:
            worst_tsb[w] = v["tsb"]
        week_end_ctl[w] = v["ctl"]   # sidste dag i ugen vinder

    for w, tsb in sorted(worst_tsb.items()):
        phase = _phase(weeks_meta, w)
        if phase == "RACE":
            continue  # race-uge: TSB vurderes på selve race-dagen i stedet
        if phase == "TAPER":
            floor = TSB_FLOOR_TAPER
        else:
            floor = TSB_FLOOR_CAMP if w in camps else TSB_FLOOR
        if tsb < floor:
            flags.append({"week": w, "rule": "tsb_floor", "level": "HARD",
                          "msg": f"TSB {tsb} i uge {w} under gulv {floor}"
                                 + (" (camp)" if w in camps else "")
                                 + (" (taper)" if phase == "TAPER" else "")})

    prev = None
    for w in sorted(week_end_ctl):
        if prev is not None:
            ramp = week_end_ctl[w] - prev
            phase = _phase(weeks_meta, w)
            if phase in ("TAPER", "RACE"):
                # CTL SKAL falde her — negativ ramp er korrekt, stigning er fejl
                if ramp > TAPER_RAMP_RISE_WARN:
                    flags.append({"week": w, "rule": "taper_ctl_rising", "level": "WARN",
                                  "msg": f"CTL stiger +{ramp:.1f} i {phase.lower()}-uge {w} — belastningen skal ned"})
            elif ramp > RAMP_HARD:
                flags.append({"week": w, "rule": "ctl_ramp", "level": "HARD",
                              "msg": f"CTL-ramp +{ramp:.1f} i uge {w} (hårdt loft {RAMP_HARD:.0f})"})
            elif ramp > RAMP_SOFT:
                flags.append({"week": w, "rule": "ctl_ramp", "level": "WARN",
                              "msg": f"CTL-ramp +{ramp:.1f} i uge {w} (blødt loft {RAMP_SOFT:.0f})"})
        prev = week_end_ctl[w]

    # Race-dags-readiness: TSB på hver race-dag bør ligge i +5..+25.
    # Håndterer dobbelt-race (Christiansborg 29/8 + Médoc 5/9, 7 dage imellem):
    # begge datoer checkes individuelt; TSB vedligeholdes imellem, genopbygges ikke.
    for r in plan.get("races", []):
        d_iso = r.get("date")
        v = proj.get(d_iso)
        if not v:
            continue
        w = _week_no(d_iso, plan_start)
        name = r.get("name", d_iso)
        if v["tsb"] < RACE_TSB_MIN:
            flags.append({"week": w, "rule": "race_tsb", "level": "WARN",
                          "msg": f"TSB {v['tsb']} på race-dag ({name}) — mål +{RACE_TSB_MIN} til +15"})
        elif v["tsb"] > RACE_TSB_MAX:
            flags.append({"week": w, "rule": "race_tsb", "level": "WARN",
                          "msg": f"TSB {v['tsb']} på race-dag ({name}) — over +{RACE_TSB_MAX}, mulig overtaper"})
    return flags


def validate(plan, seed_ctl=None, seed_atl=None, seed_date=None, athlete="kennet"):
    """Samlet validering. Uden seed køres kun strukturregler."""
    flags = structural_flags(plan, athlete=athlete)
    if seed_ctl is not None and athlete == "kennet":
        flags += load_flags(plan, seed_ctl, seed_atl, seed_date)
    actuals = plan["athletes"].get(athlete, {}).get("actualsThroughWeek", 0)
    for f in flags:
        f["historic"] = f["week"] <= actuals
    return sorted(flags, key=lambda f: (f["historic"] is False, f["week"], f["rule"]))
