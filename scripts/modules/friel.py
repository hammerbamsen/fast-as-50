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
løbe-regler er HARD (undtagen fortløbende løbedage = WARN fra 27/9-2026), ramp/TSB er HARD ved brud på hårdt loft, WARN ved blødt.
"""
from datetime import date, timedelta

try:
    from . import programs as _programs
    from . import bike_library as _bike_library
except ImportError:  # test_friel.py importerer modulet som top-level
    import programs as _programs
    import bike_library as _bike_library

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

# --- Friels 2. udgave (maj 2026), skrevet ind 27/11-2026 ---------------------
# Friel smed 1. udgaves manuskript ud og vendte positionen: masters-atleter
# laver nu for meget intensitet og for lidt lav intensitet. Reglerne nedenfor er
# hans egne tal. De fem er WARN, ikke HARD — de maa kunne bekraeftes vaek, fordi
# klassifikationen af udendoers pas og loeb sker paa pasnavn og kan tage fejl.
MAX_HARD_PER_WEEK = 2            # "faa senioratleter kan haandtere mere end to"
HARD_GAP_H = 48                  # minimum mellem to haarde pas
HARD_GAP_Z5_H = 72               # er begge Z5: 3 dage er oftest bedre end 2
MIN_EASY_DAYS = 3                # 5-2: hoejst 2 haarde + 2 moderate pr. uge
# Friel skriver "ca. 15 min" samlet rep-tid i Z5 pr. pas. Loftet staar paa 16,
# fordi 4x4 (16 min) er et kendt protokol og ikke skal flage paa ét minut —
# Kennets beslutning 27/11-2026. Over 16 flager: 4x4-clark (18) og
# Ronnestad 30/15 (20) er reelt over hans tal.
MAX_Z5_MIN_PER_SESSION = 16      # samlet rep-tid i Z5 pr. pas (Friel: ca. 15)
MAX_LOAD_WEEKS_BEFORE_RR = 2     # to belastningsuger, saa 5 dages R&R
Z5_PCT_FLOOR = 105               # % af FTP der regnes som Z5 i bike_library-steps

# Navnemarkoerer til pas UDEN libraryId — udendoers ture og alle loeb. Rammer
# kun klassifikationen; kaelderpas laeses altid fra bike_library.load_of().
HARD_NAME_MARKERS = ("vo2", "taerskel", "tærskel", "over-under", "over/under",
                     "norsk", "intervaller", "sprint", "pr-forsøg", "pr-forsoeg",
                     "z4", "z5", "ftp-test")
EASY_NAME_MARKERS = ("z1", "z2", "rolig", "let", "restitution", "teknisk",
                     "vandring", "gang", "shakeout", "aabner", "åbner")
# Styrke taeller i samlet belastning, men ikke i max-2-haarde (CLAUDE.md regel 4).
NEVER_HARD_TYPES = ("Swim", "Hike", "Walk", "WeightTraining", "Yoga", "Other")
LOAD_BLOCKS = ("BUILD", "CAMP", "SPECIFIK", "STELVIO", "PEAK")

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


def entry_load(entry):
    """'haard' | 'moderat' | 'let' | None for et planlagt pas.

    Kilderaekkefoelge, jf. CLAUDE.md regel 3 — belastningen staar i feltet
    `load`, den udledes ikke af kategorien:
      1. libraryId -> bike_library.load_of()  (kaelderpas, autoritativt)
      2. pasnavn   -> navnemarkoerer           (udendoers ture og loeb)
    None betyder "taeller ikke med": styrke, svoem, vandring og tomme dage.
    """
    wo = (entry or {}).get("workout") or {}
    wtype = wo.get("type")
    if not wtype or wtype in NEVER_HARD_TYPES:
        return None
    lid = entry.get("libraryId")
    if lid:
        try:
            return _bike_library.load_of(lid)
        except (KeyError, TypeError):
            pass
    name = (wo.get("name") or "").lower()
    if any(m in name for m in EASY_NAME_MARKERS):
        return "let"
    if any(m in name for m in HARD_NAME_MARKERS):
        return "haard"
    return "moderat"


def planned_z5_min(entry):
    """Planlagte minutter >= Z5_PCT_FLOOR % af FTP i et kaelderpas.

    Kun pas med libraryId kan maales: et udendoers pas har ingen steps.
    Returnerer 0 naar der ikke er noget at maale.
    """
    lid = (entry or {}).get("libraryId")
    if not lid:
        return 0.0
    try:
        steps = _bike_library.get(lid).get("steps") or []
    except (KeyError, TypeError):
        return 0.0
    total = 0.0

    def walk(items, mult=1):
        nonlocal total
        for st in items:
            if st.get("type") == "reps":
                walk(st.get("steps") or [], mult * (st.get("n") or 1))
                continue
            pct = st.get("pct")
            if pct is None and st.get("to") is not None:
                pct = (st.get("from") or 0 + st["to"]) / 2
            if pct is not None and pct >= Z5_PCT_FLOOR:
                total += (st.get("min") or 0) * mult

    walk(steps)
    return total


def _is_z5_session(entry):
    """Z5-pas: planlagt Z5-tid, eller et navn/libraryId der markerer VO2."""
    if planned_z5_min(entry) > 0:
        return True
    wo = (entry or {}).get("workout") or {}
    return _is_vo2(wo)


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


def edition2_flags(plan, athlete="kennet", today=None):
    """Regel 1, 2, 3 og 5 fra Friels 2. udgave (27/11-2026).

    Regel 4 (R&R efter to belastningsuger) ligger i structural_flags, hvor
    recovery-reglen allerede boede.

    Alle fire er WARN. Klassifikationen af udendoers pas og loeb sker paa
    pasnavn (entry_load), og den kan tage fejl — en HARD-gate paa et gaet ville
    blokere rigtige planaendringer.
    """
    flags = []
    program = _program(plan, athlete, today)
    plan_start = date.fromisoformat(program["start"])
    total_weeks = program["totalWeeks"]
    weeks_meta = _programs.weeks_meta(program)
    days = plan["athletes"][athlete]["days"]
    race_dates = {r.get("date") for r in (program.get("races") or []) if r.get("date")}

    # pr. uge: haarde dage, moderate dage, lette/fri dage. Og en flad liste af
    # haarde pas med dato, saa afstanden mellem dem kan maales paa tvaers af uger.
    per_week = {}
    hard_sessions = []
    for d in days:
        w = _week_no(d["date"], plan_start)
        if not 1 <= w <= total_weeks or d["date"] in race_dates:
            continue
        bucket = per_week.setdefault(w, {"haard": 0, "moderat": 0, "let": 0})
        loads, z5, hard_names = set(), False, []
        for e in d["entries"]:
            lo = entry_load(e)
            if lo:
                loads.add(lo)
            if lo == "haard":
                hard_names.append(((e.get("workout") or {}).get("name") or "pas"))
                if _is_z5_session(e):
                    z5 = True
            # Regel 5: loftet for Z5-tid i ETT pas
            z5_min = planned_z5_min(e)
            if z5_min > MAX_Z5_MIN_PER_SESSION:
                flags.append({
                    "week": w, "rule": "z5_per_session", "level": "WARN",
                    "msg": f"{round(z5_min)} min Z5 i ét pas {d['date']} "
                           f"({(e.get('workout') or {}).get('name') or 'pas'}) — "
                           f"Friel: ca. {MAX_Z5_MIN_PER_SESSION} min"})
        if "haard" in loads:
            bucket["haard"] += 1
            hard_sessions.append({"date": date.fromisoformat(d["date"]), "week": w,
                                  "z5": z5, "name": hard_names[0] if hard_names else "pas"})
        elif "moderat" in loads:
            bucket["moderat"] += 1
        else:
            bucket["let"] += 1

    for w, b in sorted(per_week.items()):
        bt = (weeks_meta.get(w, {}).get("blockType") or "").upper()
        if bt.startswith(("TAPER", "RACE")):
            continue
        # Regel 1: max 2 haarde dage pr. uge, paa tvaers af discipliner.
        # bike_library.check_week() taeller kun cykelpas, saa et haardt loeb
        # tirsdag + VO2 paa cyklen torsdag gik ubemaerket igennem.
        if b["haard"] > MAX_HARD_PER_WEEK:
            flags.append({"week": w, "rule": "hard_per_week", "level": "WARN",
                          "msg": f"{b['haard']} hårde dage i uge {_iso(plan_start, w)} "
                                 f"(Friel: max {MAX_HARD_PER_WEEK}, alle discipliner)"})
        # Regel 3: 5-2 — mindst 3 dage om ugen helt lette eller fri.
        # Kun uger der faktisk er planlagt hele vejen igennem.
        if sum(b.values()) >= 7 and b["let"] < MIN_EASY_DAYS:
            flags.append({"week": w, "rule": "easy_days_min", "level": "WARN",
                          "msg": f"Kun {b['let']} lette dage i uge {_iso(plan_start, w)} "
                                 f"(Friel 5-2: mindst {MIN_EASY_DAYS})"})

    # Regel 2: afstand mellem haarde pas. 48 timer normalt, 72 naar begge er Z5.
    hard_sessions.sort(key=lambda h: h["date"])
    for a, b in zip(hard_sessions, hard_sessions[1:]):
        timer = (b["date"] - a["date"]).days * 24
        kraev = HARD_GAP_Z5_H if (a["z5"] and b["z5"]) else HARD_GAP_H
        if timer < kraev:
            bt = (weeks_meta.get(b["week"], {}).get("blockType") or "").upper()
            if bt.startswith(("TAPER", "RACE")):
                continue
            flags.append({
                "week": b["week"], "rule": "hard_spacing", "level": "WARN",
                "msg": f"{timer} t mellem hårde pas {a['date'].isoformat()} og "
                       f"{b['date'].isoformat()} (kræver {kraev} t"
                       f"{' — begge Z5' if kraev == HARD_GAP_Z5_H else ''})"})
    return flags


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

    # Fortløbende løbedage — WARN (Kennet 27/9-2026: "tilsidesæt gate" —
    # kan bekræftes væk med confirmedWarn; max 3 løb/uge er stadig HARD)
    run_dates.sort()
    for a, b in zip(run_dates, run_dates[1:]):
        if (b - a).days == 1:
            w = _week_no(b.isoformat(), plan_start)
            if not _load_rules_apply(w):
                continue
            flags.append({"week": w, "rule": "consecutive_runs", "level": "WARN",
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

    # Regel 4 (Friel 2. udgave, 27/11-2026): R&R efter TO belastningsuger, ikke
    # tre. Hans mesocyklus er 2 belastnings-mikrocykler + 5 dages R&R. CAMP og
    # SPECIFIK taeller nu med som belastning — foer saa reglen kun BUILD, saa en
    # lejr efterfulgt af to build-uger gik ubemaerket igennem.
    streak = 0
    for w in range(1, total_weeks + 1):
        bt = (weeks_meta.get(w, {}).get("blockType") or "").upper()
        if bt.startswith(LOAD_BLOCKS):
            streak += 1
            if streak > MAX_LOAD_WEEKS_BEFORE_RR:
                flags.append({"week": w, "rule": "missing_recovery", "level": "WARN",
                              "msg": f"{streak}. belastningsuge i træk uden R&R "
                                     f"(uge {_iso(plan_start, w)}, Friel: max "
                                     f"{MAX_LOAD_WEEKS_BEFORE_RR} + 5 dage)"})
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
    flags += edition2_flags(plan, athlete=athlete, today=today)
    if seed_ctl is not None and athlete == "kennet":
        flags += load_flags(plan, seed_ctl, seed_atl, seed_date,
                            readiness=readiness, current_week=current_week, today=today)
    actuals = _programs.actuals_through_week(plan, athlete, _program(plan, athlete, today))
    for f in flags:
        f["historic"] = f["week"] <= actuals
    return sorted(flags, key=lambda f: (f["historic"] is False, f["week"], f["rule"]))
