#!/usr/bin/env python3
"""
Fast as Fifty — 14-ugers program til Intervals.icu
Datoer verificeret mod Outlook-kalender.

Uge  1: 01-07 jun  BUILD    Gentofte
Uge  2: 08-14 jun  BUILD+   Man-Ons Gentofte | Tor-Søn Mallorca #1
Uge  3: 15-21 jun  BUILD+   Man-Ons Mallorca | Tor hjem | Fre-Søn Gentofte
Uge  4: 22-28 jun  RECOVERY Gentofte
Uge  5: 29jun-5jul BUILD    Gentofte
Uge  6: 06-12 jul  BUILD    Gentofte
Uge  7: 13-19 jul  RECOVERY Gentofte
Uge  8: 20-26 jul  BUILD    Gentofte
Uge  9: 27jul-2aug BUILD    Gentofte | Fre-Søn Musik i Gentofte
Uge 10: 03-09 aug  BUILD+   Man-Lør Gentofte | Søn fly Mallorca #2
Uge 11: 10-16 aug  BUILD+   Man-Søn Mallorca #2 (hjem søn 16.)
Uge 12: 17-23 aug  TAPER    Gentofte | Lør Norge start
Uge 13: 24-30 aug  TAPER    Mon Norge hjem | Lør CHRISTIANSBORG RUNDT
Uge 14: 31aug-6sep RACE     Tor fly Bordeaux | Lør MARATHON MÉDOC

Opdatering juni 2026:
- description bruger absolut pace/watt (officielt Intervals format)
- workout_doc bruger %pace/%ftp (bekræftet virker til Garmin-struktur)
- delete_existing filtrerer korrekt på category=WORKOUT
"""

import json, sys, time, requests
from datetime import date, timedelta

ATHLETE_ID = "i599466"
BASE       = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
PLAN_START = date(2026, 6, 1)
FTP        = 270   # watt
THRESHOLD  = 260   # sek/km = 4:20/km

# ── Zone-definitioner ───────────────────────────────────────────
# Løb: absolut pace til description | %pace til workout_doc
RUN_ZONES = {
    "Z1": {"desc": ">5:35/km",       "doc": {"start": 65,  "end": 78,  "units": "%pace"}},
    "Z2": {"desc": "4:56-5:34/km",   "doc": {"start": 78,  "end": 88,  "units": "%pace"}},
    "Z3": {"desc": "4:26-4:55/km",   "doc": {"start": 88,  "end": 98,  "units": "%pace"}},
    "Z4": {"desc": "4:13-4:25/km",   "doc": {"start": 98,  "end": 103, "units": "%pace"}},
    "Z5": {"desc": "3:53-4:05/km",   "doc": {"start": 106, "end": 110, "units": "%pace"}},
}

# Cykel: absolut % FTP til description | %ftp til workout_doc
BIKE_ZONES = {
    "Z1": {"desc": "44-56% FTP",  "doc": {"start": 44,  "end": 56,  "units": "%ftp"}},
    "Z2": {"desc": "56-76% FTP",  "doc": {"start": 56,  "end": 76,  "units": "%ftp"}},
    "Z3": {"desc": "76-91% FTP",  "doc": {"start": 76,  "end": 91,  "units": "%ftp"}},
    "Z4": {"desc": "91-100% FTP", "doc": {"start": 91,  "end": 100, "units": "%ftp"}},
    "Z5": {"desc": "106-115% FTP","doc": {"start": 106, "end": 115, "units": "%ftp"}},
}

# ── Step-builders — returnerer {desc, doc} ──────────────────────
def s_run(dur_min, zone, label):
    z = RUN_ZONES[zone]
    return {
        "desc": f"- {label} {dur_min}m {z['desc']} Pace",
        "doc":  {"text": label, "pace": z["doc"], "duration": dur_min * 60}
    }

def s_bike(dur_min, zone, label):
    z = BIKE_ZONES[zone]
    return {
        "desc": f"- {label} {dur_min}m {z['desc']}",
        "doc":  {"text": label, "power": z["doc"], "duration": dur_min * 60}
    }

def s_free(dur_min, label):
    return {
        "desc": f"- {label} {dur_min}m freeride",
        "doc":  {"text": label, "duration": dur_min * 60}
    }

def s_reps(n, steps):
    inner_desc = "\n".join(s["desc"] for s in steps)
    return {
        "desc": f"\n{n}x\n{inner_desc}\n",
        "doc":  {"reps": n, "text": f"{n}x", "steps": [s["doc"] for s in steps]}
    }

def build(steps):
    """Saml liste af step-dicts til description-tekst og workout_doc."""
    desc = "\n".join(s["desc"] for s in steps).strip()
    doc  = {"steps": [s["doc"] for s in steps]}
    return desc, doc

# ── Workout-bibliotek ───────────────────────────────────────────
def run_z2(tot_min, wu=10, cd=5):
    main = tot_min - wu - cd
    desc, doc = build([
        s_run(wu,   "Z1", "Varm-op"),
        s_run(main, "Z2", "Base"),
        s_run(cd,   "Z1", "Cool-down"),
    ])
    return {"name": f"Løb Z2 {tot_min} min", "type": "Run",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def run_z2_lang(tot_min):
    desc, doc = build([
        s_run(15,            "Z1", "Varm-op"),
        s_run(tot_min - 25,  "Z2", "Lang base"),
        s_run(10,            "Z1", "Cool-down"),
    ])
    return {"name": f"Lang løb Z2 {tot_min} min", "type": "Run",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def run_z2_z3_marathon(tot_min=135):
    desc, doc = build([
        s_run(15,            "Z1", "Varm-op"),
        s_run(tot_min - 45,  "Z2", "Base"),
        s_run(20,            "Z3", "Marathon-push"),
        s_run(10,            "Z1", "Cool-down"),
    ])
    return {"name": f"Lang løb Z2+Z3 marathon {tot_min} min", "type": "Run",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def run_vo2_5x3():
    desc, doc = build([
        s_run(15, "Z1", "Varm-op"),
        s_reps(5, [s_run(3, "Z4", "Interval"), s_run(2, "Z1", "Pause")]),
        s_run(10, "Z1", "Cool-down"),
    ])
    return {"name": "Løb VO2 5×3 min Z4", "type": "Run",
            "moving_time": 65*60, "description": desc, "workout_doc": doc}

def run_vo2_4x5():
    desc, doc = build([
        s_run(15, "Z1", "Varm-op"),
        s_reps(4, [s_run(5, "Z4", "Interval"), s_run(3, "Z1", "Pause")]),
        s_run(10, "Z1", "Cool-down"),
    ])
    return {"name": "Løb VO2 4×5 min Z4-Z5", "type": "Run",
            "moving_time": 70*60, "description": desc, "workout_doc": doc}

def run_vo2_6x3_z5():
    desc, doc = build([
        s_run(15, "Z1", "Varm-op"),
        s_reps(6, [s_run(3, "Z5", "Z5 interval"), s_run(2, "Z1", "Pause")]),
        s_run(10, "Z1", "Cool-down"),
    ])
    return {"name": "Løb VO2 6×3 min Z5", "type": "Run",
            "moving_time": 70*60, "description": desc, "workout_doc": doc}

def run_vo2_4x5_z5():
    desc, doc = build([
        s_run(15, "Z1", "Varm-op"),
        s_reps(4, [s_run(5, "Z5", "Z5 interval"), s_run(3, "Z1", "Pause")]),
        s_run(10, "Z1", "Cool-down"),
    ])
    return {"name": "Løb VO2 4×5 min Z5 peak", "type": "Run",
            "moving_time": 75*60, "description": desc, "workout_doc": doc}

def run_vo2_taper():
    desc, doc = build([
        s_run(10, "Z1", "Varm-op"),
        s_reps(4, [s_run(3, "Z4", "Interval"), s_run(2, "Z1", "Pause")]),
        s_run(10, "Z1", "Cool-down"),
    ])
    return {"name": "Løb VO2 taper 4×3 Z4", "type": "Run",
            "moving_time": 55*60, "description": desc, "workout_doc": doc}

def run_shakeout():
    desc, doc = build([
        s_run(10,  "Z1", "Let løb"),
        s_reps(4,  [s_free(1, "Stride 20 sek"), s_free(1, "Jog 40 sek")]),
        s_run(5,   "Z1", "Cool-down"),
    ])
    return {"name": "Shakeout løb + strides", "type": "Run",
            "moving_time": 20*60, "description": desc, "workout_doc": doc}

def run_let(tot_min=35):
    desc, doc = build([s_run(tot_min, "Z1", "Let løb")])
    return {"name": f"Løb let Z1 {tot_min} min", "type": "Run",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def bike_z2(tot_min, location=""):
    name = f"Cykel Z2 {tot_min} min" + (f" {location}" if location else "")
    desc, doc = build([
        s_bike(10,          "Z1", "Varm-op"),
        s_bike(tot_min-15,  "Z2", "Aerob base"),
        s_bike(5,           "Z1", "Cool-down"),
    ])
    return {"name": name, "type": "Ride",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def bike_5x3_z4():
    desc, doc = build([
        s_bike(15, "Z2", "Varm-op"),
        s_reps(5, [s_bike(3, "Z4", "Interval"), s_bike(3, "Z1", "Pause")]),
        s_bike(15, "Z2", "Cool-down"),
    ])
    return {"name": "Cykel 5×3 min Z4", "type": "Ride",
            "moving_time": 65*60, "description": desc, "workout_doc": doc}

def bike_bjerg_z4(location="Mallorca"):
    desc, doc = build([
        s_bike(30, "Z2", "Varm-op til bjerg"),
        s_reps(5, [s_bike(7, "Z4", "Z4 opstigning"), s_bike(4, "Z1", "Ned")]),
        s_bike(25, "Z2", "Cool-down hjem"),
    ])
    return {"name": f"Cykel bjerg-intervaller Z4 {location}", "type": "Ride",
            "moving_time": 120*60, "description": desc, "workout_doc": doc}

def bike_z2_z3(tot_min=80):
    main = tot_min - 40
    desc, doc = build([
        s_bike(20,   "Z2", "Varm-op"),
        s_bike(main, "Z3", "Z3 blok"),
        s_bike(20,   "Z2", "Cool-down"),
    ])
    return {"name": f"Hometrainer Z2-Z3 {tot_min} min", "type": "Ride",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def bike_3x15_z3(tot_min=90):
    desc, doc = build([
        s_bike(15, "Z2", "Varm-op"),
        s_reps(3, [s_bike(15, "Z3", "Z3 interval"), s_bike(5, "Z2", "Pause")]),
        s_bike(15, "Z2", "Cool-down"),
    ])
    return {"name": f"Hometrainer 3×15 min Z3 {tot_min} min", "type": "Ride",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def swim_2000():
    desc, doc = build([
        s_free(10, "400m varm-op Z1"),
        s_reps(6,  [s_free(2, "100m teknik Z2")]),
        s_reps(8,  [s_free(2, "100m moderat Z3"), s_free(1, "30s pause")]),
        s_free(10, "400m cool Z1"),
    ])
    return {"name": "Svøm 2000m teknisk", "type": "Swim",
            "moving_time": 60*60, "description": desc, "workout_doc": doc}

def swim_2500():
    desc, doc = build([
        s_free(10, "400m varm-op"),
        s_reps(5,  [s_free(4, "200m Z3"), s_free(1, "30s pause")]),
        s_free(8,  "400m teknik"),
        s_free(5,  "300m cool"),
    ])
    return {"name": "Svøm 2500m", "type": "Swim",
            "moving_time": 65*60, "description": desc, "workout_doc": doc}

def swim_let():
    desc, doc = build([
        s_free(8,  "400m varm-op Z1"),
        s_reps(5,  [s_free(2, "100m teknik Z1-Z2")]),
        s_free(6,  "300m cool"),
    ])
    return {"name": "Svøm 1500m let teknisk", "type": "Swim",
            "moving_time": 45*60, "description": desc, "workout_doc": doc}

def strength_a(sets=3):
    desc, doc = build([
        s_reps(sets, [
            s_free(1, "Thruster 12.5kg ×10"),
            s_free(1, "Renegade Row ×8"),
            s_free(1, "Push-up ×10"),
            s_free(1, "KB Swing 16kg ×15"),
            s_free(1, "RDL ×10"),
            s_free(1, "Bulgarian Split Squat ×8/ben"),
            s_free(2, "Pause 90 sek"),
        ]),
        s_free(30, "Walk Z1"),
    ])
    return {"name": f"Styrke A Functional Strength {sets} sæt", "type": "WeightTraining",
            "moving_time": 60*60, "description": desc, "workout_doc": doc}

def strength_let():
    desc, doc = build([
        s_reps(2, [
            s_free(1, "Thruster 10kg ×10"),
            s_free(1, "Push-up ×8"),
            s_free(1, "KB Swing 12.5kg ×12"),
            s_free(1, "RDL ×10"),
            s_free(2, "Pause 90 sek"),
        ]),
    ])
    return {"name": "Styrke let 2 sæt recovery", "type": "WeightTraining",
            "moving_time": 40*60, "description": desc, "workout_doc": doc}

# ── 14-ugers plan ───────────────────────────────────────────────
def make_plan():
    p = PLAN_START
    return [
    # ── UGE 1: 1-7 jun  BUILD ───────────────────────────────────
    (p+timedelta(0),  strength_a(3),         "Styrke A + walk"),
    (p+timedelta(1),  run_z2(55),            "Løb Z2 easy"),
    (p+timedelta(2),  run_z2(65),            "Løb Z2 medium"),
    (p+timedelta(3),  strength_a(2),         "Styrke B let + walk"),
    (p+timedelta(4),  bike_5x3_z4(),         "Cykel 5×3 Z4"),
    (p+timedelta(5),  run_z2_lang(100),      "Lang løb Z2 100 min"),
    (p+timedelta(6),  swim_2000(),           "Svøm 2000m + cykel let"),

    # ── UGE 2: 8-14 jun  BUILD+ ─────────────────────────────────
    (p+timedelta(7),  strength_a(3),         "Styrke A Gentofte"),
    (p+timedelta(8),  run_z2(45),            "Løb Z2 45 min tidlig — workshop dag 1"),
    (p+timedelta(9),  run_z2(45),            "Løb Z2 45 min tidlig — workshop dag 2"),
    (p+timedelta(10), bike_z2(60,"Mallorca"),"Aktivering cykel Z2 60 min — ankomst Mallorca"),
    (p+timedelta(11), bike_bjerg_z4(),       "Cykel bjerg Z4 — VO2 stimulus Mallorca"),
    (p+timedelta(12), bike_z2(150,"Mallorca"),"Cykel Z2 lang 2.5t Mallorca"),
    (p+timedelta(13), swim_let(),            "Open water svøm + cykel let Mallorca"),

    # ── UGE 3: 15-21 jun  BUILD+ ────────────────────────────────
    (p+timedelta(14), bike_bjerg_z4(),       "Cykel bjerg Z4 Mallorca"),
    (p+timedelta(15), run_z2(60),            "Løb Z2 60 min Mallorca"),
    (p+timedelta(16), bike_z2(60,"Mallorca"),"Cykel let recovery Mallorca"),
    (p+timedelta(17), None,                  "Hjemrejse (tor 18. jun)"),
    (p+timedelta(18), run_z2(50),            "Løb Z2 let Gentofte — frokost Alice"),
    (p+timedelta(19), bike_z2(60),           "Hometrainer Z2 60 min"),
    (p+timedelta(20), strength_a(3),         "Styrke A + svøm 1500m"),

    # ── UGE 4: 22-28 jun  RECOVERY ──────────────────────────────
    (p+timedelta(21), None,                  "Hvile — walk"),
    (p+timedelta(22), run_let(30),           "Løb let 30 min"),
    (p+timedelta(23), swim_let(),            "Svøm let 1500m"),
    (p+timedelta(24), strength_let(),        "Styrke let"),
    (p+timedelta(25), bike_z2(45),           "Cykel Z1 let 45 min"),
    (p+timedelta(26), run_z2(65),            "Løb medium Z2 65 min"),
    (p+timedelta(27), None,                  "Hvile / walk"),

    # ── UGE 5: 29 jun–5 jul  BUILD ──────────────────────────────
    (p+timedelta(28), strength_a(3),         "Styrke A + cykel Z2"),
    (p+timedelta(29), run_vo2_5x3(),         "Løb VO2 5×3 Z4"),
    (p+timedelta(30), bike_z2(75),           "Hometrainer Z2 75 min"),
    (p+timedelta(31), run_z2(65),            "Løb Z2 65 min"),
    (p+timedelta(32), strength_let(),        "Styrke B"),
    (p+timedelta(33), run_z2_lang(115),      "Lang løb Z2 115 min"),
    (p+timedelta(34), swim_2000(),           "Svøm 2000m"),

    # ── UGE 6: 6-12 jul  BUILD ──────────────────────────────────
    (p+timedelta(35), strength_a(3),         "Styrke A + cykel Z2 60 min"),
    (p+timedelta(36), run_vo2_4x5(),         "Løb VO2 4×5 Z4-Z5"),
    (p+timedelta(37), bike_z2_z3(80),        "Hometrainer Z2-Z3 80 min"),
    (p+timedelta(38), run_z2(70),            "Løb Z2 70 min"),
    (p+timedelta(39), swim_2000(),           "Svøm 2000m"),
    (p+timedelta(40), run_z2_lang(125),      "Lang løb Z2 125 min"),
    (p+timedelta(41), bike_z2(90),           "Cykel Z2 udendørs 90 min"),

    # ── UGE 7: 13-19 jul  RECOVERY ──────────────────────────────
    (p+timedelta(42), None,                  "Hvile"),
    (p+timedelta(43), run_let(35),           "Løb let 35 min"),
    (p+timedelta(44), swim_let(),            "Svøm let 1500m"),
    (p+timedelta(45), strength_let(),        "Styrke let"),
    (p+timedelta(46), bike_z2(50),           "Cykel let 50 min"),
    (p+timedelta(47), run_z2(70),            "Løb Z2 medium 70 min"),
    (p+timedelta(48), None,                  "Hvile"),

    # ── UGE 8: 20-26 jul  BUILD ─────────────────────────────────
    (p+timedelta(49), strength_a(3),         "Styrke A + cykel Z2 60 min"),
    (p+timedelta(50), run_vo2_6x3_z5(),      "Løb VO2 6×3 Z5"),
    (p+timedelta(51), bike_z2_z3(90),        "Hometrainer Z2-Z3 90 min"),
    (p+timedelta(52), run_z2(70),            "Løb Z2 70 min"),
    (p+timedelta(53), swim_2500(),           "Svøm 2500m"),
    (p+timedelta(54), run_z2_lang(130),      "Lang løb Z2 130 min"),
    (p+timedelta(55), bike_z2(120),          "Cykel Z2 lang 2t"),

    # ── UGE 9: 27 jul–2 aug  BUILD ──────────────────────────────
    (p+timedelta(56), strength_a(3),         "Styrke A tung + cykel 60 min"),
    (p+timedelta(57), run_vo2_4x5_z5(),      "Løb VO2 4×5 Z5 peak"),
    (p+timedelta(58), bike_3x15_z3(90),      "Hometrainer 3×15 Z3"),
    (p+timedelta(59), run_z2(75),            "Løb Z2 75 min"),
    (p+timedelta(60), None,                  "Musik i Gentofte — hvile (fre 31. jul)"),
    (p+timedelta(61), run_z2_lang(90),       "Lang løb Z2 90 min — Musik i Gentofte"),
    (p+timedelta(62), swim_let(),            "Svøm let — Musik i Gentofte (søn 2. aug)"),

    # ── UGE 10: 3-9 aug  BUILD+ ─────────────────────────────────
    (p+timedelta(63), bike_z2(60),           "Cykel Z2 60 min Gentofte"),
    (p+timedelta(64), run_z2(75),            "Løb Z2 75 min — Hudlæge"),
    (p+timedelta(65), bike_3x15_z3(90),      "Hometrainer 3×15 Z3"),
    (p+timedelta(66), run_z2_lang(110),      "Lang løb Z2 110 min"),
    (p+timedelta(67), swim_2000(),           "Svøm 2000m"),
    (p+timedelta(68), run_z2_lang(100),      "Lang løb Z2 100 min — Frokost Alice"),
    (p+timedelta(69), None,                  "Fly → Mallorca #2 (søn 9. aug)"),

    # ── UGE 11: 10-16 aug  BUILD+ ───────────────────────────────
    (p+timedelta(70), bike_z2(180,"Mallorca"),"Cykel base lang 3t Mallorca"),
    (p+timedelta(71), run_z2(75),            "Løb Z2 75 min Mallorca"),
    (p+timedelta(72), bike_bjerg_z4(),       "Cykel bjerg Z4 Mallorca"),
    (p+timedelta(73), run_z2_lang(120),      "Lang løb Z2 120 min Mallorca"),
    (p+timedelta(74), swim_2000(),           "Svøm 2000m Mallorca"),
    (p+timedelta(75), bike_z2(210,"Mallorca"),"Cykel Z2 peak 3.5t Mallorca"),
    (p+timedelta(76), None,                  "Hjemrejse Mallorca (søn 16. aug)"),

    # ── UGE 12: 17-23 aug  TAPER ────────────────────────────────
    (p+timedelta(77), strength_let(),        "Styrke let"),
    (p+timedelta(78), run_vo2_taper(),       "Løb VO2 taper 4×3"),
    (p+timedelta(79), bike_z2(50),           "Hometrainer Z2 50 min"),
    (p+timedelta(80), run_z2(60),            "Løb Z2 60 min"),
    (p+timedelta(81), None,                  "Hvile"),
    (p+timedelta(82), None,                  "Norge start (lør 22. aug)"),
    (p+timedelta(83), run_let(30),           "Let løb Norge (søn 23. aug)"),

    # ── UGE 13: 24-30 aug  TAPER ────────────────────────────────
    (p+timedelta(84), None,                  "Hjem fra Norge (man 24. aug)"),
    (p+timedelta(85), bike_z2(40),           "Cykel let 40 min"),
    (p+timedelta(86), run_shakeout(),        "Løb Z2 + strides"),
    (p+timedelta(87), None,                  "Hvile"),
    (p+timedelta(88), None,                  "Hvile"),
    (p+timedelta(89), None,                  "⭐ CHRISTIANSBORG RUNDT (lør 29. aug)"),
    (p+timedelta(90), None,                  "Recovery walk"),

    # ── UGE 14: 31 aug–6 sep  RACE ──────────────────────────────
    (p+timedelta(91), run_let(25),           "Løb let 25 min"),
    (p+timedelta(92), run_shakeout(),        "Let løb + strides"),
    (p+timedelta(93), None,                  "Hvile total"),
    (p+timedelta(94), None,                  "Fly → Bordeaux (tor 3. sep)"),
    (p+timedelta(95), None,                  "Hotel Bordeaux — hvile (fre 4. sep)"),
    (p+timedelta(96), None,                  "🏆 MARATHON MÉDOC (lør 5. sep)"),
    (p+timedelta(97), None,                  "Recovery Bordeaux (søn 6. sep)"),
    ]

# ── Upload-hjælpere ─────────────────────────────────────────────
def delete_existing(session, dt):
    """Slet alle WORKOUT-events på datoen — undgår dubletter."""
    try:
        r = session.get(f"{BASE}/events", params={
            "oldest": f"{dt.isoformat()}T00:00:00",
            "newest": f"{dt.isoformat()}T23:59:00"
        })
        if r.status_code != 200:
            return
        for ev in (r.json() if isinstance(r.json(), list) else []):
            if ev.get("category") == "WORKOUT":
                rd = session.delete(f"{BASE}/events/{ev['id']}")
                if rd.status_code in (200, 204):
                    print(f"    🗑️  Slettede: {ev.get('name')} ({ev['id']})")
    except Exception as e:
        print(f"    ⚠️  delete fejl {dt}: {e}")

def upload(session, wo, dt):
    if wo is None:
        return None
    delete_existing(session, dt)

    payload = {
        "name":             wo["name"],
        "type":             wo["type"],
        "start_date_local": f"{dt.isoformat()}T00:00:00",
        "end_date_local":   f"{dt.isoformat()}T23:59:00",
        "moving_time":      wo.get("moving_time", 3600),
        "category":         "WORKOUT",
        "description":      wo.get("description", ""),
        "workout_doc":      wo.get("workout_doc", {}),
    }

    for attempt in range(3):
        r = session.post(f"{BASE}/events", json=payload)
        if r.status_code in (200, 201):
            eid = r.json().get("id", "?")
            print(f"  ✅ {dt.strftime('%d. %b %a')} — {wo['name']} (id:{eid})")
            return eid
        elif r.status_code == 429:
            print(f"  ⏳ Rate limit — venter 5 sek...")
            time.sleep(5)
        else:
            print(f"  ❌ {dt.strftime('%d. %b %a')} — {r.status_code}: {r.text[:150]}")
            return None
    return None

# ── Main ────────────────────────────────────────────────────────
def run_plan(session, week_filter=0):
    plan     = make_plan()
    days_da  = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]
    ok = skip = err = 0
    cur_week = 0

    for dt, wo, note in plan:
        week = (dt - PLAN_START).days // 7 + 1
        if week_filter > 0 and week != week_filter:
            continue
        if week != cur_week:
            cur_week = week
            print(f"\n📅 UGE {week} ({dt.strftime('%d. %b')})")
        if wo is None:
            print(f"  ⚪ {dt.strftime('%d. %b')} {days_da[dt.weekday()]} — {note}")
            skip += 1
            continue
        eid = upload(session, wo, dt)
        if eid: ok += 1
        else:   err += 1
        time.sleep(1.0)

    return ok, skip, err

def main():
    import os
    api_key    = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("INTERVALS_API_KEY","")
    week_arg   = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.environ.get("WEEK_ONLY","0"))

    if not api_key:
        print("Mangler API-nøgle. Brug: python3 build_workouts.py API_NOEGLE [uge]")
        sys.exit(1)

    session = requests.Session()
    session.auth = ("API_KEY", api_key)
    session.headers["Content-Type"] = "application/json"

    r = session.get(BASE)
    if r.status_code != 200:
        print(f"❌ Forbindelsesfejl: {r.status_code}")
        sys.exit(1)
    print(f"✅ Forbundet: {r.json().get('name', ATHLETE_ID)}\n")

    total_ok = total_skip = total_err = 0

    if week_arg == -1:
        # Alle 14 uger
        print("Uploader alle 14 uger...")
        ok, skip, err = run_plan(session, week_filter=0)
        total_ok += ok; total_skip += skip; total_err += err
    elif week_arg == 0:
        # Auto: fra aktuel uge til 14
        current_week = min(max((date.today() - PLAN_START).days // 7 + 1, 1), 14)
        print(f"Auto-tilstand: uploader uge {current_week}–14")
        for w in range(current_week, 15):
            ok, skip, err = run_plan(session, week_filter=w)
            total_ok += ok; total_skip += skip; total_err += err
    else:
        # Specifik uge
        ok, skip, err = run_plan(session, week_filter=week_arg)
        total_ok += ok; total_skip += skip; total_err += err

    print(f"\n{'='*50}")
    print(f"✅ Uploadet:    {total_ok}")
    print(f"⚪ Hvile/rejse: {total_skip}")
    print(f"❌ Fejl:        {total_err}")
    if total_err > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()

