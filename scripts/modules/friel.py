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

try:
    from . import programs as _programs
except ImportError:  # test_friel.py importerer modulet som top-level
    import programs as _programs

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

# T1 — Wellness-integration: morgen-readiness justerer den AKTUELLE uges
# TSB-gulv dynamisk. LOW strammer (flager tidligere = "reducér"), HIGH giver
# lidt mere plads. Kun aktuel uge — dagens readiness må ikke ændre uge 12's
# projektion. Camp-gulvet (-35) beholder sin dybde ved NORMAL/HIGH, men
# strammes til -25 ved LOW (den farligste kombination: camp + upresset krop).
READINESS_FLOOR = {"LOW": -25, "NORMAL": -30, "HIGH": -32}
READINESS_HRV_DROP_PCT = 10.0   # HRV-fald ift. 7d-snit der markerer LOW
READINESS_SLEEP_LOW = 6.0       # søvn under dette = LOW
READINESS_SLEEP_HIGH = 7.0      # søvn ved/over dette (+ HRV≥snit) = HIGH


def readiness_band(hrv_today, hrv_avg, sleep_last):
    """Morgen-readiness -> 'LOW' | 'NORMAL' | 'HIGH'.

    LOW  : HRV-fald > 10% ift. 7d-snit, ELLER søvn < 6t.
    HIGH : HRV >= 7d-snit OG søvn >= 7t (begge signaler skal være til stede).
    NORMAL: alt andet, inkl. manglende data (intet signal -> ingen justering).
    """
    low = False
    high = True
    if hrv_today and hrv_avg and hrv_avg > 0:
        drop = (hrv_avg - hrv_today) / hrv_avg * 100.0
        if drop > READINESS_HRV_DROP_PCT:
            low = True
        if hrv_today < hrv_avg:
            high = False
    else:
        high = False   # uden HRV-signal kan vi ikke bekræfte HIGH
    if sleep_last is not None:
        if sleep_last < READINESS_SLEEP_LOW:
            low = True
        if sleep_last < READINESS_SLEEP_HIGH:
            high = False
    else:
        high = False   # uden søvn-signal kan vi ikke bekræfte HIGH
    if low:
        return "LOW"
    if high:
        return "HIGH"
    return "NORMAL"


def _phase(weeks_meta, w):
    """Normaliseret fase for uge w. Ukendt/manglende blockType -> ''
    (= hidtidig adfærd, bagudkompatibelt).

    Blok-typer på tværs af programmer:
      BUILD, BUILD+, SPECIFIK, SPECIFIK+, STELVIO, PEAK, CAMP -> "BUILD" (belastning)
      BASE, BASE+, TRANSITION                                -> "BASE"
      RECOVERY / TAPER / RACE                                -> uændret
    """
    bt = ((weeks_meta.get(w) or {}).get("blockType") or "").upper()
    if bt.startswith(("BUILD", "SPECIFIK", "STELVIO", "PEAK", "CAMP")):
        return "BUILD"
    if bt.startswith(("BASE", "TRANSITION")):
        return "BASE"
    if bt in ("RECOVERY", "TAPER", "RACE"):
        return bt
    return ""


def _program(plan, athlete="kennet", today=None):
    """Det aktive program for atleten (programs.py) — eneste kilde til start,
    totalWeeks, weeks og races i dette modul. Legacy-fixtures uden `programs`
    syntetiseres automatisk, så gamle tests virker uændret."""
    p = _programs.active_program(plan, athlete, today)
    if p is None:
        raise KeyError(f"Intet program for atlet {athlete!r} i plan.json")
    return p

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


def _iso(plan_start, w):
    """Programuge w → kalenderuge (ISO) til tekster. Kennet læser kun kalenderuger (26/9-2026)."""
    return (plan_start + timedelta(weeks=w - 1)).isocalendar()[1]


def _camp_weeks(plan, program=None):
    """Uger med rejse-ophold markeret som camp (Mallorca) — TSB-gulv -35."""
    camps = set()
    program = program or _program(plan)
    plan_start = date.fromisoformat(program["start"])
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
            if 1 <= w <= program["totalWeeks"]:
                camps.add(w)
            d += timedelta(days=1)
    return camps


def structural_flags(plan, athlete="kennet", today=None):
    """Regler der kun kræver dagslisten: løb/uge, fortløbende løb, VO2, recovery-placering.
    Uger regnes relativt til atletens AKTIVE program pr. `today`."""
    flags = []
    program = _program(plan, athlete, today)
    plan_start = date.fromisoformat(program["start"])
    days = plan["athletes"][athlete]["days"]
    weeks_meta = _programs.weeks_meta(program)
    total_weeks = program["totalWeeks"]

    runs_per_week = {w: 0 for w in range(1, total_weeks + 1)}
    vo2_per_week = {w: 0 for w in range(1, total_weeks + 1)}
    planned_weeks = set()   # uger med mindst én dag i dagslisten (endnu ikke planlagte uger flagges ikke)
    run_dates = []

    # Løbsdage er ikke træningspas. Selve løbet (og taper/race-ugernes
    # bevidst hyppige, korte shakeouts) må ikke udløse max_runs /
    # consecutive_runs — ellers står de to vigtigste uger permanent røde og
    # de ægte signaler drukner.
    race_dates = {r.get("date") for r in (program.get("races") or []) if r.get("date")}

    def _load_rules_apply(week_no):
        bt = (weeks_meta.get(week_no, {}).get("blockType") or "").upper()
        return not bt.startswith(("TAPER", "RACE"))

    for d in days:
        w = _week_no(d["date"], plan_start)
        if not 1 <= w <= total_weeks:
            continue
        planned_weeks.add(w)
        if d["date"] in race_dates:
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
        if n > MAX_RUNS_PER_WEEK and _load_rules_apply(w):
            flags.append({"week": w, "rule": "max_runs", "level": "HARD",
                          "msg": f"{n} løbedage i uge {_iso(plan_start, w)} (max {MAX_RUNS_PER_WEEK})"})

    # Fortløbende løbedage — HARD
    run_dates.sort()
    for a, b in zip(run_dates, run_dates[1:]):
        if (b - a).days == 1:
            w = _week_no(b.isoformat(), plan_start)
            if not _load_rules_apply(w):
                continue
            flags.append({"week": w, "rule": "consecutive_runs", "level": "HARD",
                          "msg": f"Fortløbende løbedage {a.isoformat()} + {b.isoformat()}"})

    # VO2 1x pr. build-uge — WARN (0 eller >1). Kun uger der faktisk er
    # planlagt (har dage) — et 51-ugers program planlægges fase for fase.
    for w in range(1, total_weeks + 1):
        bt = (weeks_meta.get(w, {}).get("blockType") or "").upper()
        if bt.startswith("BUILD") and w in planned_weeks:
            if vo2_per_week[w] == 0:
                flags.append({"week": w, "rule": "vo2_missing", "level": "WARN",
                              "msg": f"Ingen VO2-stimulus i build-uge {_iso(plan_start, w)}"})
            elif vo2_per_week[w] > 1:
                flags.append({"week": w, "rule": "vo2_excess", "level": "WARN",
                              "msg": f"{vo2_per_week[w]} VO2-pas i uge {_iso(plan_start, w)} (plan: 1)"})

    # Recovery efter max 3 build-uger i træk — WARN
    streak = 0
    for w in range(1, total_weeks + 1):
        bt = (weeks_meta.get(w, {}).get("blockType") or "").upper()
        if bt.startswith("BUILD"):
            streak += 1
            if streak > 3:
                flags.append({"week": w, "rule": "missing_recovery", "level": "WARN",
                              "msg": f"{streak}. build-uge i træk uden recovery (uge {_iso(plan_start, w)})"})
        else:
            streak = 0

    return flags


def project_fitness(plan, seed_ctl, seed_atl, seed_date, today=None):
    """
    CTL/ATL/TSB-projektion pr. dag ud fra ugentlige TSS-targets (jævnt fordelt
    på træningsdage). Seedet med FAKTISK Intervals-fitness — ikke lærebogsstart.
    Returnerer {date_iso: {"ctl":…, "atl":…, "tsb":…}} fra seed-dato til planslut.

    Valgfrie entries (entry["optional"] is True) vises konservativt: dagen
    bliver i NÆVNEREN (training_days), men får 0 TSS. Uge-totalen falder
    dermed med den valgfrie dags andel — projektionen svarer til scenariet
    "passet springes over". Ville dagen også ryge ud af nævneren, blev den
    samme uge-TSS blot fordelt på færre dage, og projektionen ville være
    uændret — altså ingen effekt.
    """
    program = _program(plan, "kennet", today)
    plan_start = date.fromisoformat(program["start"])
    total_weeks = program["totalWeeks"]
    weeks_meta = _programs.weeks_meta(program)
    days = plan["athletes"]["kennet"]["days"]

    training_days = {}   # week -> antal dage med workout (valgfrie tæller MED)
    day_has_wo = {}      # dag -> har OBLIGATORISK workout (valgfrie tæller IKKE)
    for d in days:
        w = _week_no(d["date"], plan_start)
        entries = d["entries"]
        has_any = any(e.get("workout") for e in entries)
        has_required = any(e.get("workout") and not e.get("optional")
                           for e in entries)
        day_has_wo[d["date"]] = has_required
        if has_any:
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


def load_flags(plan, seed_ctl, seed_atl, seed_date,
               readiness=None, current_week=None, today=None):
    """Belastningsregler: TSB-gulv og CTL-ramp, på projekteret fitness.

    T1: readiness ('LOW'/'NORMAL'/'HIGH') justerer KUN current_week's TSB-gulv.
    readiness=None (default) -> hidtidig adfærd, fuldt bagudkompatibelt.
    """
    flags = []
    program = _program(plan, "kennet", today)
    plan_start = date.fromisoformat(program["start"])
    total_weeks = program["totalWeeks"]
    weeks_meta = _programs.weeks_meta(program)
    camps = _camp_weeks(plan, program)
    proj = project_fitness(plan, seed_ctl, seed_atl, seed_date, today=today)

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
        # T1: readiness strammer/løsner KUN den aktuelle uge (ikke taper — den
        # har sin egen skærpede logik). LOW hæver gulvet (strammer, også camp);
        # HIGH sænker det, men aldrig dybere end camp-gulvet.
        readiness_adj = False
        if (readiness in ("LOW", "HIGH") and w == current_week
                and phase != "TAPER"):
            if readiness == "LOW":
                new_floor = max(floor, READINESS_FLOOR["LOW"])
            else:  # HIGH
                new_floor = min(floor, READINESS_FLOOR["HIGH"])
            readiness_adj = new_floor != floor
            floor = new_floor
        if tsb < floor:
            flags.append({"week": w, "rule": "tsb_floor", "level": "HARD",
                          "msg": f"TSB {tsb} i uge {_iso(plan_start, w)} under gulv {floor}"
                                 + (" (camp)" if w in camps else "")
                                 + (" (taper)" if phase == "TAPER" else "")
                                 + (f" (readiness {readiness.lower()})"
                                    if readiness_adj else "")})

    prev = None
    for w in sorted(week_end_ctl):
        if prev is not None:
            ramp = week_end_ctl[w] - prev
            phase = _phase(weeks_meta, w)
            if phase in ("TAPER", "RACE"):
                # CTL SKAL falde her — negativ ramp er korrekt, stigning er fejl
                if ramp > TAPER_RAMP_RISE_WARN:
                    flags.append({"week": w, "rule": "taper_ctl_rising", "level": "WARN",
                                  "msg": f"CTL stiger +{ramp:.1f} i {phase.lower()}-uge {_iso(plan_start, w)} — belastningen skal ned"})
            elif ramp > RAMP_HARD:
                flags.append({"week": w, "rule": "ctl_ramp", "level": "HARD",
                              "msg": f"CTL-ramp +{ramp:.1f} i uge {_iso(plan_start, w)} (hårdt loft {RAMP_HARD:.0f})"})
            elif ramp > RAMP_SOFT:
                flags.append({"week": w, "rule": "ctl_ramp", "level": "WARN",
                              "msg": f"CTL-ramp +{ramp:.1f} i uge {_iso(plan_start, w)} (blødt loft {RAMP_SOFT:.0f})"})
        prev = week_end_ctl[w]

    # Race-dags-readiness: TSB på hver race-dag bør ligge i +5..+25.
    # Håndterer dobbelt-race (to løb med 7 dage imellem): begge datoer checkes
    # individuelt; TSB vedligeholdes imellem, genopbygges ikke.
    for r in program.get("races", []):
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

    # T1: rådgivende signal ved lav morgen-readiness i den aktuelle uge.
    if readiness == "LOW" and current_week and 1 <= current_week <= total_weeks:
        flags.append({"week": current_week, "rule": "low_readiness", "level": "WARN",
                      "msg": "Lav readiness i dag (HRV/søvn) — overvej at reducere "
                             "dagens/ugens belastning"})
    return flags


def validate(plan, seed_ctl=None, seed_atl=None, seed_date=None, athlete="kennet",
             readiness=None, current_week=None, today=None):
    """Samlet validering. Uden seed køres kun strukturregler.

    T1: readiness/current_week videreføres til load_flags (kun Kennet).
    Default None -> hidtidig adfærd, bagudkompatibelt.
    `today` styrer hvilket program der valideres mod (default: i dag).
    """
    flags = structural_flags(plan, athlete=athlete, today=today)
    if seed_ctl is not None and athlete == "kennet":
        flags += load_flags(plan, seed_ctl, seed_atl, seed_date,
                            readiness=readiness, current_week=current_week, today=today)
    actuals = _programs.actuals_through_week(plan, athlete, _program(plan, athlete, today))
    for f in flags:
        f["historic"] = f["week"] <= actuals
    return sorted(flags, key=lambda f: (f["historic"] is False, f["week"], f["rule"]))
