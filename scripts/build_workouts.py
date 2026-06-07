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
"""

import json, sys, time, requests
from datetime import date, timedelta

ATHLETE_ID = "i599466"
BASE = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
PLAN_START = date(2026, 6, 1)

# ── Zone helpers ────────────────────────────────────────────────
def pace_mid(p1, p2):
    """'4:56','5:34' → midpoint i sekunder/km"""
    def to_s(p): a,b = p.split(":"); return int(a)*60+int(b)
    return (to_s(p1) + to_s(p2)) // 2

def step_run(dur_min, label, p1, p2=None):
    pace = pace_mid(p1, p2) if p2 else pace_mid(p1, p1)
    desc = f"{label} ({p1}–{p2} min/km)" if p2 else f"{label} (>{p1} min/km)"
    return {"type":"step","duration":dur_min*60,"description":desc,
            "pace":{"value":pace,"units":"km"}}

def step_bike(dur_min, label, w1, w2=None):
    w = (w1+w2)//2 if w2 else w1
    desc = f"{label} ({w1}–{w2}W)" if w2 else f"{label} ({w1}W)"
    return {"type":"step","duration":dur_min*60,"description":desc,
            "power":{"value":w,"units":"watts"}}

def step_free(dur_min, label):
    return {"type":"step","duration":dur_min*60,"description":label}

def reps(n, steps):
    return {"type":"repetition","reps":n,"steps":steps}

# ── Workout library ─────────────────────────────────────────────
def run_z2(tot_min, wu=10, cd=5):
    main = tot_min - wu - cd
    return {"name":f"Løb Z2 {tot_min} min","type":"Run",
            "description":"Aerob base. Samtale-tempo.",
            "moving_time":tot_min*60,
            "workout_doc":{"steps":[
                step_run(wu,"Z1 varm-op","5:35"),
                step_run(main,"Z2 base","4:56","5:34"),
                step_run(cd,"Z1 cool","5:35")]}}

def run_z2_lang(tot_min):
    return {"name":f"Lang løb Z2 {tot_min} min","type":"Run",
            "description":"Tid på benene. Spis + drik undervejs.",
            "moving_time":tot_min*60,
            "workout_doc":{"steps":[
                step_run(15,"Z1 varm-op","5:35"),
                step_run(tot_min-25,"Z2 lang","4:56","5:34"),
                step_run(10,"Z1 cool","5:35")]}}

def run_z2_z3_marathon(tot_min=135):
    return {"name":f"Lang løb Z2+Z3 marathon {tot_min} min","type":"Run",
            "description":"Marathon-specifik. Slut 20 min Z3 simulerer træthed.",
            "moving_time":tot_min*60,
            "workout_doc":{"steps":[
                step_run(15,"Z1 varm-op","5:35"),
                step_run(tot_min-45,"Z2 base","4:56","5:34"),
                step_run(20,"Z3 push","4:26","4:55"),
                step_run(10,"Z1 cool","5:35")]}}

def run_vo2_5x3():
    return {"name":"Løb VO2 5×3 min Z4","type":"Run",
            "description":"VO2-stimulus. Start konservativt i Z4.",
            "moving_time":65*60,
            "workout_doc":{"steps":[
                step_run(15,"Z1 varm-op","5:35"),
                reps(5,[step_run(3,"Z4","4:13","4:25"),
                        step_run(2,"Z1 pause","5:35")]),
                step_run(10,"Z1 cool","5:35")]}}

def run_vo2_4x5():
    return {"name":"Løb VO2 4×5 min Z4-Z5","type":"Run",
            "description":"Progression fra 5×3. Længere intervaller.",
            "moving_time":70*60,
            "workout_doc":{"steps":[
                step_run(15,"Z1 varm-op","5:35"),
                reps(4,[step_run(5,"Z4-Z5","3:53","4:25"),
                        step_run(3,"Z1 pause","5:35")]),
                step_run(10,"Z1 cool","5:35")]}}

def run_vo2_6x3_z5():
    return {"name":"Løb VO2 6×3 min Z5","type":"Run",
            "description":"Peak VO2. Fuld Z5. Kræver god restitution.",
            "moving_time":70*60,
            "workout_doc":{"steps":[
                step_run(15,"Z1 varm-op","5:35"),
                reps(6,[step_run(3,"Z5","3:53","4:12"),
                        step_run(2,"Z1 pause","5:35")]),
                step_run(10,"Z1 cool","5:35")]}}

def run_vo2_4x5_z5():
    return {"name":"Løb VO2 4×5 min Z5 peak","type":"Run",
            "description":"Peak VO2-stimulus. Maksimal aerob kapacitet.",
            "moving_time":75*60,
            "workout_doc":{"steps":[
                step_run(15,"Z1 varm-op","5:35"),
                reps(4,[step_run(5,"Z5","3:53","4:12"),
                        step_run(3,"Z1 pause","5:35")]),
                step_run(10,"Z1 cool","5:35")]}}

def run_vo2_taper():
    return {"name":"Løb VO2 taper 4×3 Z4","type":"Run",
            "description":"Vedligehold skarphed. Kort og præcis.",
            "moving_time":55*60,
            "workout_doc":{"steps":[
                step_run(10,"Z1 varm-op","5:35"),
                reps(4,[step_run(3,"Z4","4:13","4:25"),
                        step_run(2,"Z1 pause","5:35")]),
                step_run(10,"Z1 cool","5:35")]}}

def run_shakeout():
    return {"name":"Shakeout løb + strides","type":"Run",
            "description":"Pre-race. Let. 4×20 sek strides.",
            "moving_time":20*60,
            "workout_doc":{"steps":[
                step_run(10,"Z1 let","5:35"),
                reps(4,[step_free(20,"Stride hurtig"),
                        step_free(40,"Jog let")]),
                step_run(5,"Z1 cool","5:35")]}}

def run_let(tot_min=35):
    return {"name":f"Løb let Z1-Z2 {tot_min} min","type":"Run",
            "description":"Recovery. Ingen intensitet.",
            "moving_time":tot_min*60,
            "workout_doc":{"steps":[
                step_run(tot_min,"Z1-Z2 let","5:00","5:35")]}}

def bike_z2(tot_min, location=""):
    name = f"Cykel Z2 {tot_min} min" + (f" {location}" if location else "")
    return {"name":name,"type":"Ride",
            "description":"Aerob base. Samtale-tempo.",
            "moving_time":tot_min*60,
            "workout_doc":{"steps":[
                step_bike(10,"Z1 varm-op",120,150),
                step_bike(tot_min-15,"Z2 steady",150,205),
                step_bike(5,"Z1 cool",100,140)]}}

def bike_5x3_z4():
    return {"name":"Cykel 5×3 min Z4","type":"Ride",
            "description":"VO2/threshold stimulus. FTP 270W.",
            "moving_time":65*60,
            "workout_doc":{"steps":[
                step_bike(15,"Z2 varm-op",150,205),
                reps(5,[step_bike(3,"Z4",245,285),
                        step_bike(3,"Z1 pause",100,135)]),
                step_bike(15,"Z2 cool",150,205)]}}

def bike_bjerg_z4(location="Mallorca"):
    return {"name":f"Cykel bjerg-intervaller Z4 {location}","type":"Ride",
            "description":"5×6-8 min op ad stigning Z4. Rul ned som pause.",
            "moving_time":120*60,
            "workout_doc":{"steps":[
                step_bike(30,"Z2 varm-op til bjerg",150,205),
                reps(5,[step_bike(7,"Z4 opstigning",245,285),
                        step_bike(4,"Z1 ned",80,130)]),
                step_bike(25,"Z2 cool hjem",150,205)]}}

def bike_z2_z3(tot_min=80):
    main = tot_min - 40
    return {"name":f"Hometrainer Z2-Z3 {tot_min} min","type":"Ride",
            "description":"Progression. Midterblok Z3 bygger tærskel.",
            "moving_time":tot_min*60,
            "workout_doc":{"steps":[
                step_bike(20,"Z2 varm-op",150,205),
                step_bike(main,"Z3 blok",205,245),
                step_bike(20,"Z2 cool",150,205)]}}

def bike_3x15_z3(tot_min=90):
    return {"name":f"Hometrainer 3×15 min Z3 {tot_min} min","type":"Ride",
            "description":"Tærskeltræning. 3 blokke Z3 med Z2 pause.",
            "moving_time":tot_min*60,
            "workout_doc":{"steps":[
                step_bike(15,"Z2 varm-op",150,205),
                reps(3,[step_bike(15,"Z3",205,245),
                        step_bike(5,"Z2 pause",150,205)]),
                step_bike(15,"Z2 cool",150,205)]}}

def swim_2000():
    return {"name":"Svøm 2000m teknisk","type":"Swim",
            "description":"400 varm-op. 6×100 teknik. 8×100 moderat 30s pause. 400 cool.",
            "moving_time":60*60,
            "workout_doc":{"steps":[
                step_free(10,"400m varm-op Z1"),
                reps(6,[step_free(2,"100m teknik Z2")]),
                reps(8,[step_free(2,"100m moderat Z3"),step_free(1,"30s pause")]),
                step_free(10,"400m cool Z1")]}}

def swim_2500():
    return {"name":"Svøm 2500m","type":"Swim",
            "description":"400 varm-op. 5×200 Z3. 400 teknik. 300 cool.",
            "moving_time":65*60,
            "workout_doc":{"steps":[
                step_free(10,"400m varm-op"),
                reps(5,[step_free(4,"200m Z3"),step_free(1,"30s pause")]),
                step_free(8,"400m teknik"),
                step_free(5,"300m cool")]}}

def swim_let():
    return {"name":"Svøm 1500m let teknisk","type":"Swim",
            "description":"Recovery. Fokus: teknik, lav puls.",
            "moving_time":45*60,
            "workout_doc":{"steps":[
                step_free(8,"400m varm-op Z1"),
                reps(5,[step_free(2,"100m teknik Z1-Z2")]),
                step_free(6,"300m cool")]}}

def strength_a(sets=3):
    return {"name":f"Styrke A Functional Strength {sets} sæt","type":"WeightTraining",
            "description":f"{sets} sæt: Thruster 12.5kg×10, Renegade Row×8, Push-up×10, KB Swing 16kg×15, RDL×10, Split Squat×8/ben. + 30 min walk.",
            "moving_time":60*60,
            "workout_doc":{"steps":[
                reps(sets,[
                    step_free(1,"Thruster 12.5kg ×10"),
                    step_free(1,"Renegade Row ×8"),
                    step_free(1,"Push-up ×10"),
                    step_free(1,"KB Swing 16kg ×15"),
                    step_free(1,"RDL ×10"),
                    step_free(1,"Bulgarian Split Squat ×8/ben"),
                    step_free(2,"Pause 90 sek")]),
                step_free(30,"Walk Z1")]}}

def strength_let():
    return {"name":"Styrke let 2 sæt recovery","type":"WeightTraining",
            "description":"2 sæt let: Thruster 10kg×10, Push-up×8, KB Swing 12.5kg×12, RDL×10.",
            "moving_time":40*60,
            "workout_doc":{"steps":[
                reps(2,[
                    step_free(1,"Thruster 10kg ×10"),
                    step_free(1,"Push-up ×8"),
                    step_free(1,"KB Swing 12.5kg ×12"),
                    step_free(1,"RDL ×10"),
                    step_free(2,"Pause 90 sek")])]}}

# ── 14-ugers plan med verificerede datoer ──────────────────────
# Format: (dato, workout_fn_eller_None, note)
def make_plan():
    p = date(2026,6,1)  # plan start

    return [
    # ── UGE 1: 1-7 jun  BUILD 34→37 ────────────────────────────
    (p+timedelta(0),  strength_a(3),      "Styrke A + walk"),
    (p+timedelta(1),  run_z2(55),         "Løb Z2 easy"),
    (p+timedelta(2),  run_z2(65),         "Løb Z2 medium"),
    (p+timedelta(3),  strength_a(2),      "Styrke B let + walk"),
    (p+timedelta(4),  bike_5x3_z4(),      "Cykel 5×3 Z4"),
    (p+timedelta(5),  run_z2_lang(100),   "Lang løb Z2 100 min"),
    (p+timedelta(6),  swim_2000(),        "Svøm 2000m + cykel let"),

    # ── UGE 2: 8-14 jun  BUILD+ 37→41 ──────────────────────────
    # Man 8 = Styrke | Tir-Ons = workshop (tidlig morgen) | Tor = fly 09:00 ankomst 10:30 | Fre-Søn Mallorca
    (p+timedelta(7),  strength_a(3),      "Styrke A Gentofte"),
    (p+timedelta(8),  run_z2(45),         "Løb Z2 45 min tidlig — workshop dag 1"),
    (p+timedelta(9),  run_z2(45),         "Løb Z2 45 min tidlig — workshop dag 2"),
    (p+timedelta(10), bike_z2(60,"Mallorca"), "Aktivering cykel Z2 60 min — ankomst Mallorca"),
    (p+timedelta(11), bike_bjerg_z4(),    "Cykel bjerg Z4 — VO2 stimulus Mallorca"),
    (p+timedelta(12), bike_z2(150,"Mallorca"), "Cykel Z2 lang 2.5t Mallorca"),
    (p+timedelta(13), swim_let(),         "Open water svøm + cykel let Mallorca"),

    # ── UGE 3: 15-21 jun  BUILD+ 41→45 ─────────────────────────
    # Man-Ons Mallorca | Tor 18 = hjemrejse | Fre 19 Alice | Lør-Søn Gentofte
    (p+timedelta(14), bike_bjerg_z4(),    "Cykel bjerg Z4 Mallorca"),
    (p+timedelta(15), run_z2(60),         "Løb Z2 60 min Mallorca"),
    (p+timedelta(16), bike_z2(60,"Mallorca"), "Cykel let recovery Mallorca"),
    (p+timedelta(17), None,               "Hjemrejse (tor 18. jun)"),
    (p+timedelta(18), run_z2(50),         "Løb Z2 let Gentofte — frokost Alice"),
    (p+timedelta(19), bike_z2(60),        "Hometrainer Z2 60 min"),
    (p+timedelta(20), strength_a(3),      "Styrke A + svøm 1500m"),

    # ── UGE 4: 22-28 jun  RECOVERY 45→43 ───────────────────────
    (p+timedelta(21), None,               "Hvile — walk"),
    (p+timedelta(22), run_let(30),        "Løb let 30 min"),
    (p+timedelta(23), swim_let(),         "Svøm let 1500m"),
    (p+timedelta(24), strength_let(),     "Styrke let"),
    (p+timedelta(25), bike_z2(45),        "Cykel Z1 let 45 min"),
    (p+timedelta(26), run_z2(65),         "Løb medium Z2 65 min"),
    (p+timedelta(27), None,               "Hvile / walk"),

    # ── UGE 5: 29 jun–5 jul  BUILD 43→47 ───────────────────────
    (p+timedelta(28), strength_a(3),      "Styrke A + cykel Z2"),
    (p+timedelta(29), run_vo2_5x3(),      "Løb VO2 5×3 Z4"),
    (p+timedelta(30), bike_z2(75),        "Hometrainer Z2 75 min"),
    (p+timedelta(31), run_z2(65),         "Løb Z2 65 min"),
    (p+timedelta(32), strength_let(),     "Styrke B"),
    (p+timedelta(33), run_z2_lang(115),   "Lang løb Z2 115 min"),
    (p+timedelta(34), swim_2000(),        "Svøm 2000m"),

    # ── UGE 6: 6-12 jul  BUILD 47→51 ───────────────────────────
    (p+timedelta(35), strength_a(3),      "Styrke A + cykel Z2 60 min"),
    (p+timedelta(36), run_vo2_4x5(),      "Løb VO2 4×5 Z4-Z5"),
    (p+timedelta(37), bike_z2_z3(80),     "Hometrainer Z2-Z3 80 min"),
    (p+timedelta(38), run_z2(70),         "Løb Z2 70 min"),
    (p+timedelta(39), swim_2000(),        "Svøm 2000m"),
    (p+timedelta(40), run_z2_lang(125),   "Lang løb Z2 125 min"),
    (p+timedelta(41), bike_z2(90),        "Cykel Z2 udendørs 90 min"),

    # ── UGE 7: 13-19 jul  RECOVERY 51→49 ───────────────────────
    (p+timedelta(42), None,               "Hvile"),
    (p+timedelta(43), run_let(35),        "Løb let 35 min"),
    (p+timedelta(44), swim_let(),         "Svøm let 1500m"),
    (p+timedelta(45), strength_let(),     "Styrke let"),
    (p+timedelta(46), bike_z2(50),        "Cykel let 50 min"),
    (p+timedelta(47), run_z2(70),         "Løb Z2 medium 70 min"),
    (p+timedelta(48), None,               "Hvile"),

    # ── UGE 8: 20-26 jul  BUILD 49→53 ──────────────────────────
    (p+timedelta(49), strength_a(3),      "Styrke A + cykel Z2 60 min"),
    (p+timedelta(50), run_vo2_6x3_z5(),   "Løb VO2 6×3 Z5"),
    (p+timedelta(51), bike_z2_z3(90),     "Hometrainer Z2-Z3 90 min"),
    (p+timedelta(52), run_z2(70),         "Løb Z2 70 min"),
    (p+timedelta(53), swim_2500(),        "Svøm 2500m"),
    (p+timedelta(54), run_z2_lang(130),   "Lang løb Z2 130 min"),
    (p+timedelta(55), bike_z2(120),       "Cykel Z2 lang 2t"),

    # ── UGE 9: 27 jul–2 aug  BUILD 53→57 ───────────────────────
    # Fre 31. jul–Søn 2. aug = Musik i Gentofte (lør/søn justeret)
    (p+timedelta(56), strength_a(3),      "Styrke A tung + cykel 60 min"),
    (p+timedelta(57), run_vo2_4x5_z5(),   "Løb VO2 4×5 Z5 peak"),
    (p+timedelta(58), bike_3x15_z3(90),   "Hometrainer 3×15 Z3"),
    (p+timedelta(59), run_z2(75),         "Løb Z2 75 min"),
    (p+timedelta(60), None,               "Musik i Gentofte — hvile (fre 31. jul)"),
    (p+timedelta(61), run_z2_lang(90),    "Lang løb Z2 90 min — Musik i Gentofte (lør)"),
    (p+timedelta(62), swim_let(),         "Svøm let — Musik i Gentofte (søn 2. aug)"),

    # ── UGE 10: 3-9 aug  BUILD+ 57→61 ──────────────────────────
    # Man-Lør Gentofte | Søn 9. aug = fly til Mallorca #2
    (p+timedelta(63), bike_z2(60),        "Cykel Z2 60 min Gentofte"),
    (p+timedelta(64), run_z2(75),         "Løb Z2 75 min — Hudlæge"),
    (p+timedelta(65), bike_3x15_z3(90),   "Hometrainer 3×15 Z3"),
    (p+timedelta(66), run_z2_lang(110),   "Lang løb Z2 110 min"),
    (p+timedelta(67), swim_2000(),        "Svøm 2000m"),
    (p+timedelta(68), run_z2_lang(100),   "Lang løb Z2 100 min — Frokost Alice"),
    (p+timedelta(69), None,               "Fly → Mallorca #2 (søn 9. aug)"),

    # ── UGE 11: 10-16 aug  BUILD+ 61→58 ────────────────────────
    # Hele ugen Mallorca | Søn 16. aug hjemrejse
    (p+timedelta(70), bike_z2(180,"Mallorca"), "Cykel base lang 3t Mallorca"),
    (p+timedelta(71), run_z2(75),         "Løb Z2 75 min Mallorca"),
    (p+timedelta(72), bike_bjerg_z4(),    "Cykel bjerg Z4 Mallorca"),
    (p+timedelta(73), run_z2_lang(120),   "Lang løb Z2 120 min Mallorca"),
    (p+timedelta(74), swim_2000(),        "Svøm 2000m Mallorca"),
    (p+timedelta(75), bike_z2(210,"Mallorca"), "Cykel Z2 peak 3.5t Mallorca"),
    (p+timedelta(76), None,               "Hjemrejse Mallorca (søn 16. aug)"),

    # ── UGE 12: 17-23 aug  TAPER 58→54 ─────────────────────────
    # Lør 22. aug = Norge start
    (p+timedelta(77), strength_let(),     "Styrke let"),
    (p+timedelta(78), run_vo2_taper(),    "Løb VO2 taper 4×3"),
    (p+timedelta(79), bike_z2(50),        "Hometrainer Z2 50 min"),
    (p+timedelta(80), run_z2(60),         "Løb Z2 60 min"),
    (p+timedelta(81), None,               "Hvile"),
    (p+timedelta(82), None,               "Norge start (lør 22. aug)"),
    (p+timedelta(83), run_let(30),        "Let løb Norge (søn 23. aug)"),

    # ── UGE 13: 24-30 aug  TAPER 54→50 ─────────────────────────
    # Man 24. = hjem Norge | Lør 29. aug = CHRISTIANSBORG RUNDT
    (p+timedelta(84), None,               "Hjem fra Norge (man 24. aug)"),
    (p+timedelta(85), bike_z2(40),        "Cykel let 40 min"),
    (p+timedelta(86), run_shakeout(),     "Løb Z2 + strides"),
    (p+timedelta(87), None,               "Hvile"),
    (p+timedelta(88), None,               "Hvile"),
    (p+timedelta(89), None,               "⭐ CHRISTIANSBORG RUNDT (lør 29. aug)"),
    (p+timedelta(90), None,               "Recovery walk"),

    # ── UGE 14: 31 aug–6 sep  RACE ──────────────────────────────
    # Tor 3. sep fly Bordeaux | Lør 5. sep MARATHON MÉDOC
    (p+timedelta(91), run_let(25),        "Løb let 25 min"),
    (p+timedelta(92), run_shakeout(),     "Let løb + strides"),
    (p+timedelta(93), None,               "Hvile total"),
    (p+timedelta(94), None,               "Fly → Bordeaux (tor 3. sep)"),
    (p+timedelta(95), None,               "Hotel Bordeaux — hvile (fre 4. sep)"),
    (p+timedelta(96), None,               "🏆 MARATHON MÉDOC (lør 5. sep)"),
    (p+timedelta(97), None,               "Recovery Bordeaux (søn 6. sep)"),
    ]

def delete_existing(session, dt):
    """Slet alle planned workouts på denne dato så vi undgår duplikater."""
    try:
        r = session.get(f"{BASE}/workouts", params={
            "oldest": dt.isoformat(), "newest": dt.isoformat()
        })
        if r.status_code != 200:
            print(f"  ⚠️  Kunne ikke hente workouts for {dt}: {r.status_code}")
            return
        workouts = r.json()
        if not isinstance(workouts, list):
            return
        for w in workouts:
            # Slet kun planned workouts (ikke completed activities)
            if w.get("type") and not w.get("athlete_id"):
                wid = w.get("id")
                if wid:
                    rd = session.delete(f"{BASE}/workouts/{wid}")
                    if rd.status_code in (200, 204):
                        print(f"  🗑️  Slettede: {w.get('name','?')} ({wid})")
                    else:
                        print(f"  ⚠️  Kunne ikke slette {wid}: {rd.status_code}")
    except Exception as e:
        print(f"  ⚠️  delete_existing fejl: {e}")

FOLDER_ID = None

def get_folder_id(session):
    """Hent første tilgængelige workout-mappe fra Intervals."""
    global FOLDER_ID
    if FOLDER_ID is not None:
        return FOLDER_ID
    r = session.get(f"{BASE}/folders")
    if r.status_code == 200:
        folders = r.json()
        if folders:
            FOLDER_ID = folders[0].get("id")
            print(f"  📁 Mappe: {folders[0].get('name','?')} (id:{FOLDER_ID})")
            return FOLDER_ID
    print(f"  ⚠️  Ingen mapper fundet: {r.status_code} {r.text[:100]}")
    return None

def upload(session, wo, dt):
    if wo is None:
        return None
    # Slet eksisterende planned workouts på datoen inden upload
    delete_existing(session, dt)
    folder_id = get_folder_id(session)
    payload = {**wo, "start_date_local": dt.isoformat()}
    if folder_id:
        payload["folder_id"] = folder_id
    r = session.post(f"{BASE}/workouts", json=payload)
    if r.status_code in (200,201):
        wid = r.json().get("id","?")
        print(f"  ✅ {dt.strftime('%d. %b %a')} — {wo['name']} (id:{wid})")
        return wid
    else:
        print(f"  ❌ {dt.strftime('%d. %b %a')} — {wo['name']} → {r.status_code}: {r.text[:500]}")
        print(f"     Payload keys: {list(payload.keys())}")
        return None

def main(api_key, week_only=0):
    session = requests.Session()
    session.auth = ("API_KEY", api_key)
    session.headers.update({"Content-Type":"application/json"})

    r = session.get(f"{BASE}")
    if r.status_code != 200:
        print(f"❌ Forbindelsesfejl: {r.status_code} — {r.text[:200]}")
        sys.exit(1)
    print(f"✅ Forbundet: {r.json().get('name', ATHLETE_ID)}\n")
    print(f"   Base URL: {BASE}")

    plan = make_plan()
    days_da = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]

    ok = skip = err = 0
    cur_week = 0

    for dt, wo, note in plan:
        # Hvis week_only > 0, spring andre uger over
        delta_check = (dt - PLAN_START).days
        week_check = delta_check // 7 + 1
        if week_only > 0 and week_check != week_only:
            continue
        delta = (dt - PLAN_START).days
        week = delta // 7 + 1
        if week != cur_week:
            cur_week = week
            print(f"\n📅 UGE {week} ({dt.strftime('%d. %b')})")

        if wo is None:
            print(f"  ⚪ {dt.strftime('%d. %b')} {days_da[dt.weekday()]} — {note}")
            skip += 1
            continue

        wid = upload(session, wo, dt)
        if wid: ok += 1
        else: err += 1
        time.sleep(0.3)

    print(f"\n{'='*50}")
    print(f"✅ Uploadet:  {ok}")
    print(f"⚪ Hvile/rejse: {skip}")
    print(f"❌ Fejl:      {err}")
    if err > 0:
        print("\n⚠️  Der var fejl — se detaljer ovenfor")
        sys.exit(1)

if __name__ == "__main__":
    import os
    api_key = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("INTERVALS_API_KEY", "")
    week_only = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.environ.get("WEEK_ONLY", "0"))
    if not api_key:
        print("Mangler INTERVALS_API_KEY")
        sys.exit(1)
    main(api_key, week_only=week_only)
