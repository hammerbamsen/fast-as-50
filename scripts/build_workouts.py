#!/usr/bin/env python3
"""
Fast as Fifty — upload af Kennets plan (data/plan.json) til Intervals.icu
Uger regnes i det AKTIVE program (modules/programs.py) — programmet vælges
efter dato, så scriptet virker på tværs af medoc-2026, tds-2027 osv.

Historisk uge-oversigt for medoc-2026 (bevaret som dokumentation):
Uge  1: 01-07 jun  BUILD    Gentofte
Uge  2: 08-14 jun  BUILD+   Man-Ons Gentofte | Tor-Søn Mallorca #1
Uge  3: 15-21 jun  BUILD+   Man-Ons Mallorca | Tor hjem | Fre-Søn Gentofte
Uge  4: 22-28 jun  RECOVERY Gentofte
Uge  5: 29jun-5jul BUILD    Gentofte
Uge  6: 06-12 jul  RECOVERY Man-Tir Gentofte | Ons-Søn Wales
Uge  7: 13-19 jul  RECOVERY Gentofte
Uge  8: 20-26 jul  BUILD    Gentofte
Uge  9: 27jul-2aug BUILD    Gentofte | Fre-Søn Musik i Gentofte
Uge 10: 03-09 aug  BUILD+   Man-Lør Gentofte | Søn fly Mallorca #2
Uge 11: 10-16 aug  BUILD+   Man-Søn Mallorca #2 (hjem søn 16.)
Uge 12: 17-23 aug  TAPER    Gentofte | Lør Norge start
Uge 13: 24-30 aug  TAPER    Mon Norge hjem | Lør CHRISTIANSBORG RUNDT
Uge 14: 31aug-6sep RACE     Tor fly Bordeaux | Lør MARATHON MÉDOC

VIGTIGT: Dette script er MASTERPLANEN for alle workouts.
Intervals.icu er master for selve træningspassene — opdateres KUN via dette script.
Garmin og Outlook synkroniseres fra Intervals (delete_existing rydder gamle pas).

Opdatering juni 2026:
- description bruger absolut pace/watt (officielt Intervals format)
- workout_doc bruger %pace/%ftp (bekræftet virker til Garmin-struktur)
- delete_existing filtrerer korrekt på category=WORKOUT
"""

import json, math, os, sys, time, requests
from datetime import date, timedelta

ATHLETE_ID  = "i599466"
BASE        = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
# FTP/THRESHOLD er FJERNET (28/7-2026). De var døde konstanter — intet i
# scriptet læste dem. Sandheden er data/plan.json -> athletes.kennet.zones.
# ── Microsoft Graph / Outlook Calendar ─────────────────────────
GRAPH_BASE   = "https://graph.microsoft.com/v1.0"
AZURE_TENANT = "003c17d1-406c-4f3a-ba81-5ac09bf49036"
AZURE_CLIENT = "d6cc8ce4-b681-4b87-8873-5d302b91f8bf"  # Fast as Fifty Calendar
OUTLOOK_CAL  = "kennet@hammerby.com"

def get_graph_token():
    import os, json as _json, time
    token_file = os.path.expanduser("~/.fast50_graph_token.json")
    if os.path.exists(token_file):
        with open(token_file) as f:
            t = _json.load(f)
        if t.get("expires_at", 0) > time.time() + 60:
            return t["access_token"]
    client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
    if not client_secret:
        print("    ⚠️  AZURE_CLIENT_SECRET ikke sat — Outlook sync springes over")
        return None
    r = requests.post(
        f"https://login.microsoftonline.com/{AZURE_TENANT}/oauth2/v2.0/token",
        data={"grant_type": "client_credentials", "client_id": AZURE_CLIENT,
              "client_secret": client_secret, "scope": "https://graph.microsoft.com/.default"},
        timeout=15)
    if r.status_code != 200:
        print(f"    ⚠️  Graph token fejl: {r.status_code}")
        return None
    td = r.json()
    td["expires_at"] = time.time() + td.get("expires_in", 3600) - 60
    with open(token_file, "w") as f:
        _json.dump(td, f)
    return td["access_token"]

def outlook_delete_by_date(dt):
    """Slet alle Træning-events på dato via Graph API."""
    token = get_graph_token()
    if not token: return
    start = f"{dt.isoformat()}T00:00:00"
    end   = f"{dt.isoformat()}T23:59:59"
    r = requests.get(
        f"{GRAPH_BASE}/users/{OUTLOOK_CAL}/calendarView",
        headers={"Authorization": f"Bearer {token}"},
        params={"startDateTime": start, "endDateTime": end,
                "$select": "id,subject,categories", "$top": "20"},
        timeout=15)
    if r.status_code != 200:
        return
    for ev in r.json().get("value", []):
        cats = " ".join(ev.get("categories", [])).encode("ascii", "ignore").decode().lower()
        subj = ev.get("subject", "").encode("ascii", "ignore").decode().lower()
        if "ning" in cats or "ning" in subj or "cykel" in subj or "l" + chr(248) + "b" in subj or "swim" in subj or "styrke" in subj or "svøm" in subj.lower():
            rd = requests.delete(
                f"{GRAPH_BASE}/users/{OUTLOOK_CAL}/events/{ev['id']}",
                headers={"Authorization": f"Bearer {token}"}, timeout=15)
            if rd.status_code in (200, 204):
                print(f"    📅 Outlook slettet: {ev['subject']}")

def outlook_create(payload):
    token = get_graph_token()
    if not token: return None
    body = {
        "subject": payload["subject"],
        "start":   {"dateTime": payload["start"], "timeZone": "Europe/Copenhagen"},
        "end":     {"dateTime": payload["end"],   "timeZone": "Europe/Copenhagen"},
        "body":    {"contentType": "text", "content": payload.get("body", "")},
        "location": {"displayName": payload.get("location", "")},
        "categories": [payload.get("categories", "Træning")],
    }
    r = requests.post(f"{GRAPH_BASE}/users/{OUTLOOK_CAL}/events",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body, timeout=15)
    if r.status_code in (200, 201):
        print("    📅 Outlook oprettet: OK")
        return r.json().get("id")
    print(f"    ⚠️  Outlook opret fejl: {r.status_code} {r.text[:100]}")
    return None

def notify_make(action, event_id=None, payload=None, dt=None):
    """Dispatcher — kalder Graph direkte."""
    if action == "delete" and dt:
        outlook_delete_by_date(dt)
    elif action == "create" and payload:
        outlook_create(payload)

# ── Sandhedslaget: data/plan.json ───────────────────────────────
PLAN_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "plan.json")

def load_plan_json():
    """Sandhedslaget: data/plan.json (v3) — begge atleter, alle dage."""
    with open(PLAN_JSON, encoding="utf-8") as f:
        return json.load(f)

# Det aktive program vælges efter dagens dato via modules/programs.py (3/9-2026).
# Før var start/totalWeeks læst fra det ene legacy 'program'-felt, som frøs
# på sidste uge når programmet sluttede. Nu: plan.json -> programs.<id>.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules import programs as _programs
ACTIVE_PROGRAM = _programs.active_program(load_plan_json(), "kennet")
PLAN_START     = date.fromisoformat(ACTIVE_PROGRAM["start"])
TOTAL_WEEKS    = ACTIVE_PROGRAM["totalWeeks"]

# ── Zone-definitioner ───────────────────────────────────────────
# INGEN hardkodede pace-strenge (28/7-2026). Teksten UDLEDES af
# thresholdSec i plan.json + den %pace-band passet faktisk bruger.
# Ren matematik: hurtig = ceil(thr*100/hi), langsom = ceil(thr*100/lo)-1.
# Ændrer du threshold ét sted, følger alt med.
RUN_DOC_PCT = {
    "Z1": (65,  78),
    "Z2": (78,  88),
    "Z3": (88,  98),
    "Z4": (98, 103),
    "Z5": (106, 110),
}

def _threshold_sec():
    return load_plan_json()["athletes"]["kennet"]["zones"]["thresholdSec"]

def _fmt_pace(sec):
    return f"{int(sec)//60}:{int(sec)%60:02d}"

def _pace_text(thr, lo, hi):
    fast = math.ceil(thr * 100 / hi)
    if lo <= 65:                       # åben restitutionsband
        return ">" + _fmt_pace(fast) + "/km"
    return f"{_fmt_pace(fast)}-{_fmt_pace(math.ceil(thr * 100 / lo) - 1)}/km"

def _build_run_zones():
    thr = _threshold_sec()
    return {z: {"desc": _pace_text(thr, lo, hi),
                "doc": {"start": lo, "end": hi, "units": "%pace"}}
            for z, (lo, hi) in RUN_DOC_PCT.items()}

RUN_ZONES = _build_run_zones()

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
        "doc":  {"text": f"{label} {z['desc']}", "pace": z["doc"], "duration": dur_min * 60}
    }

def s_bike(dur_min, zone, label):
    z = BIKE_ZONES[zone]
    return {
        "desc": f"- {label} {dur_min}m {z['desc']}",
        "doc":  {"text": f"{label} {z['desc']}", "power": z["doc"], "duration": dur_min * 60}
    }

def s_free(dur_min, label):
    return {
        "desc": f"- {label} {dur_min}m freeride",
        "doc":  {"text": label, "duration": dur_min * 60}
    }

def s_bike_ramp(dur_min, start, end, label, kind=None):
    """Ægte ramp-step til cykel — Intervals markerer ramp:true, watt stiger/falder lineært."""
    d = {"ramp": True, "power": {"start": start, "end": end, "units": "%ftp"}, "duration": dur_min * 60}
    if kind:
        d[kind] = True
    return {"desc": f"- {label} {dur_min}m ramp {start}-{end}% FTP", "doc": d}

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
        s_bike_ramp(10, 45, 68, "Varm-op", "warmup"),
        s_bike(tot_min-15,  "Z2", "Aerob base"),
        s_bike_ramp(5, 68, 45, "Cool-down", "cooldown"),
    ])
    return {"name": name, "type": "Ride",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def bike_5x3_z4():
    desc, doc = build([
        s_bike_ramp(15, 50, 80, "Varm-op", "warmup"),
        s_reps(5, [s_bike(3, "Z4", "Interval"), s_bike(3, "Z1", "Pause")]),
        s_bike_ramp(15, 80, 50, "Cool-down", "cooldown"),
    ])
    return {"name": "Cykel 5×3 min Z4", "type": "Ride",
            "moving_time": 65*60, "description": desc, "workout_doc": doc}

def bike_bjerg_z4(location="Mallorca"):
    desc, doc = build([
        s_bike_ramp(30, 50, 76, "Varm-op til bjerg", "warmup"),
        s_reps(5, [s_bike(7, "Z4", "Z4 opstigning"), s_bike(4, "Z1", "Ned")]),
        s_bike_ramp(25, 76, 50, "Cool-down hjem", "cooldown"),
    ])
    return {"name": f"Cykel bjerg-intervaller Z4 {location}", "type": "Ride",
            "moving_time": 120*60, "description": desc, "workout_doc": doc}

def bike_formentor():
    desc, doc = build([
        s_bike_ramp(30, 45, 70, "Varm-op", "warmup"),
        s_bike(240, "Z2", "Formentor lang tur"),
        s_bike(60,  "Z3", "Klatre-sektioner Formentor"),
        s_bike_ramp(30, 70, 45, "Cool-down hjem", "cooldown"),
    ])
    return {"name": "Cykel Formentor 149km", "type": "Ride",
            "moving_time": 360*60, "description": desc, "workout_doc": doc}

def hike_easy(tot_min=90):
    desc, doc = build([s_free(tot_min, "Hike Z1-Z2")])
    return {"name": f"Hike let {tot_min} min", "type": "Hike",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def bike_z2_z3(tot_min=80):
    main = tot_min - 40
    desc, doc = build([
        s_bike_ramp(20, 45, 76, "Varm-op", "warmup"),
        s_bike(main, "Z3", "Z3 blok"),
        s_bike_ramp(20, 76, 45, "Cool-down", "cooldown"),
    ])
    return {"name": f"Hometrainer Z2-Z3 {tot_min} min", "type": "Ride",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def bike_3x15_z3(tot_min=90):
    desc, doc = build([
        s_bike_ramp(15, 50, 76, "Varm-op", "warmup"),
        s_reps(3, [s_bike(15, "Z3", "Z3 interval"), s_bike(5, "Z2", "Pause")]),
        s_bike_ramp(15, 76, 50, "Cool-down", "cooldown"),
    ])
    return {"name": f"Hometrainer 3×15 min Z3 {tot_min} min", "type": "Ride",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def bike_hundested():
    desc = (
        "Lang Z2 cykeltur fra Charlottenlund til Hundested. "
        "Ca. 65-70 km. Hold Z2 hele vejen — lav kadence, kontrolleret indsats. "
        "Frokost i Hundested bagefter."
    )
    return {"name": "Cykel Z2 til Hundested", "type": "Ride",
            "moving_time": 9000, "description": desc, "workout_doc": None}

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

def swim_recovery(tot_min=30):
    desc, doc = build([
        s_free(8,  "300m varm-op Z1"),
        s_reps(4,  [s_free(2, "100m teknik Z1-Z2")]),
        s_free(6,  "300m cool"),
    ])
    return {"name": f"Svøm let {tot_min} min recovery", "type": "Swim",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

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

def run_long_km(km, tot_min):
    """Langtur navngivet i km (marathon-ladder mod Médoc)."""
    desc, doc = build([
        s_run(15,           "Z1", "Varm-op"),
        s_run(tot_min - 25, "Z2", f"Lang base {km} km"),
        s_run(10,           "Z1", "Cool-down"),
    ])
    return {"name": f"Lang løb Z2 {km} km ({tot_min} min)", "type": "Run",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def run_trail(tot_min, label="Trail-løb Z2 Wales"):
    """Trail-løb efter tid og følelse — Z2 på puls/åndedræt, terræn styrer pace."""
    desc, doc = build([
        s_run(10,           "Z1", "Varm-op"),
        s_free(tot_min-15,  f"{label} — Z2-indsats, pace følger terræn"),
        s_run(5,            "Z1", "Cool-down"),
    ])
    return {"name": f"{label} {tot_min} min", "type": "Run",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

def bike_ftp_test():
    """20-min FTP-test — resultatet opdaterer FTP og watt-zoner i Intervals."""
    desc, doc = build([
        s_bike_ramp(20, 45, 72, "Varm-op progressiv", "warmup"),
        s_bike(5,  "Z4", "Aktivering 5 min"),
        s_bike(5,  "Z1", "Let"),
        s_free(20, "20 MIN ALL-OUT TEST — jævn max-indsats"),
        s_bike_ramp(15, 60, 40, "Cool-down", "cooldown"),
    ])
    return {"name": "FTP-TEST 20 min (opdatér zoner efter)", "type": "Ride",
            "moving_time": 65*60,
            "description": desc + "\n\nEfter testen: nyt FTP = 95% af 20-min snit-watt. Opdatér i Intervals → Settings.",
            "workout_doc": doc}

def run_threshold_test():
    """20-min løbetest — threshold = 95% af testens gennemsnitsFART.
    Pace divideres med 0,95 (~ x1,053). Gang ALDRIG pace med 0,95."""
    desc, doc = build([
        s_run(15, "Z1", "Varm-op"),
        s_reps(3, [s_free(1, "Stride 20 sek"), s_free(1, "Jog 40 sek")]),
        s_free(20, "20 MIN TEST — jævn max-indsats, flad rute"),
        s_run(10, "Z1", "Cool-down"),
    ])
    return {"name": "THRESHOLD-TEST løb 20 min (opdatér pace-zoner efter)", "type": "Run",
            "moving_time": 55*60,
            "description": desc + "\n\nEfter testen: threshold-pace = 95% af testens gennemsnitsfart (snit-pace / 0,95). Opdatér zoner i Intervals + plan.json.",
            "workout_doc": doc}

def ow_swim(tot_min=45, label="Open water"):
    """Åbent vand — Christiansborg-forberedelse. Sigtning, våddragt, start-rutine."""
    desc, doc = build([
        s_free(10, "Tilvænning + let svøm langs kant"),
        s_free(tot_min-20, f"{label}: kontinuerlig svøm, sigtning hver 8.-10. tag"),
        s_free(10, "Let ud-svøm + exit-rutine"),
    ])
    return {"name": f"OW-svøm {label} {tot_min} min", "type": "OpenWaterSwim",
            "moving_time": tot_min*60, "description": desc, "workout_doc": doc}

# ── Kaelder-bibliotek (data/bike_library.json) ──────────────────
# Én kilde til sandhed for indendørs cykelpas. Samme JSON genererer
# Zwift-.zwo-filerne via scripts/build_zwo.py, så de to aldrig drifter.
def bike_lib(workout_id):
    """Hent et kaelderpas fra biblioteket i samme format som funktionerne ovenfor."""
    from modules import bike_library
    return bike_library.to_intervals(workout_id)


def bike_sa_calobra():
    """Sa Calobra via Puig Major — tidlig afgang, op ad Puig Major, ned til Sa Calobra,
    de 26 sving op igen, retur. Stor fjeld-Z2-dag med Z3 på selve stigningerne."""
    desc, doc = build([
        s_bike_ramp(20, 45, 68, "Varm-op — tidlig udrulning", "warmup"),
        s_bike(90, "Z2", "Puig Major opstigning — jævn Z2"),
        s_bike(35, "Z2", "Nedkørsel til Sa Calobra — kontrolleret, pas på bremser"),
        s_bike(35, "Z3", "Sa Calobra op — 26 sving, jævn Z3"),
        s_bike(80, "Z2", "Retur Z2 base hjem"),
        s_bike_ramp(20, 68, 45, "Cool-down", "cooldown"),
    ])
    return {"name": "Cykel Sa Calobra via Puig Major", "type": "Ride",
            "moving_time": 280*60, "description": desc, "workout_doc": doc}

# ── Plan (læses fra plan.json) ─────────────────────────────────

def make_plan():
    """Kennets plan som (date, workout_dict|None, note)-tupler — læst fra plan.json.
    Workout-biblioteket ovenfor bruges fremover til at GENERERE nye entries i
    plan.json, ikke som runtime-kilde."""
    plan = load_plan_json()
    out = []
    for d in plan["athletes"]["kennet"]["days"]:
        dt = date.fromisoformat(d["date"])
        if not d.get("entries"):
            # Dagen er RYDDET i planen (fx et forslag der fjernede svømningen).
            # Den skal stadig besøges af run_plan, ellers bliver et gammelt
            # event stående i Intervals og Outlook for evigt: sletningen sker
            # kun på datoer der optræder her. Fundet ved QA 9/9-2026, hvor fire
            # svømmepas 2/10-30/10 stod tilbage efter forslaget til uge 3-8.
            # None = hviledag, samme behandling som en dag uden pas.
            out.append((dt, None, d.get("note") or "ingen pas i planen"))
            continue
        for e in d["entries"]:
            wo = e.get("workout")
            # Valgfrit pas: markér i selve event-navnet, så det er synligt i
            # Intervals og Outlook. Kopi — plan.json's navn røres ikke.
            if wo and e.get("optional") and "(valgfri)" not in wo.get("name", "").lower():
                wo = {**wo, "name": f"{wo.get('name', '')} (valgfri)"}
            out.append((dt, wo, e.get("note", "")))
    return out

def friel_report():
    """Kør Friel-validering mod plan.json og print flags. Blokerer ikke i fase 1."""
    try:
        from modules import friel
        plan = load_plan_json()
        seed = plan.get("fitnessSeed", {}).get("current", {})
        flags = friel.validate(plan, seed_ctl=seed.get("ctl"),
                               seed_atl=seed.get("atl"), seed_date=seed.get("date"))
        if not flags:
            print("Friel: ingen flags\n")
            return
        active = [f for f in flags if not f.get("historic")]
        hist = [f for f in flags if f.get("historic")]
        print(f"Friel: {len(active)} aktive flag(s), {len(hist)} historiske (uge 1-{load_plan_json()['athletes']['kennet'].get('actualsThroughWeek', 0)}):")
        for f in active:
            print(f"  [{f['level']}] uge {f['week']}: {f['msg']}")
        for f in hist:
            print(f"  [historik/{f['level']}] uge {f['week']}: {f['msg']}")
        print()
    except Exception as e:
        print(f"Friel-rapport sprang over: {e}\n")

# ── Upload-hjælpere ─────────────────────────────────────────────
# Tidspunkt-overrides for dage hvor standardtid (se _start_hour) ikke
# passer med Kennets skema (job/møder/workshop fylder standard-vinduet).
def _load_time_overrides():
    """To formater, begge understøttet (28/7-2026):
         "2026-06-25": [16, 0]            -> gælder hele dagen
         "2026-08-06": {"Run": [15, 30]}  -> gælder kun den disciplin
    Dict-formatet kom til fordi en dag kan have svøm 06:00 OG løb 15:30,
    og det gamle format kun kunne rumme ét tidspunkt pr. dato."""
    try:
        raw = load_plan_json()["athletes"]["kennet"].get("timeOverrides", {})
        out = {}
        for k, v in raw.items():
            dt = date.fromisoformat(k)
            if isinstance(v, dict):
                out[dt] = {sp.lower(): tuple(t) for sp, t in v.items()}
            else:
                out[dt] = tuple(v)
        return out
    except Exception:
        return {}

TIME_OVERRIDES = _load_time_overrides()

def _start_hour(wo_type):
    """Starttidspunkt baseret på disciplin."""
    t = (wo_type or "").upper()
    if t in ("SWIM", "OW"):           return 6, 0
    if t in ("RUN", "TRAIL_RUN"):     return 6, 30
    if t in ("RIDE", "VIRTUAL_RIDE"): return 7, 0
    if t in ("WEIGHT_TRAINING", "WEIGHTTRAINING", "WEIGHTS"):     return 7, 0
    return 6, 0  # fallback

def _start_end(wo, dt):
    """Returner (start_iso, end_iso) for et workout."""
    ov = TIME_OVERRIDES.get(dt)
    if isinstance(ov, dict):
        hit = ov.get((wo.get("type") or "").lower())
        sh, sm = hit if hit else _start_hour(wo.get("type", ""))
    elif ov:
        sh, sm = ov
    else:
        sh, sm = _start_hour(wo.get("type", ""))
    start_mins = sh * 60 + sm
    duration_mins = wo.get("moving_time", 3600) // 60
    end_mins = start_mins + duration_mins
    eh, em = end_mins // 60, end_mins % 60
    return (
        f"{dt.isoformat()}T{sh:02d}:{sm:02d}:00",
        f"{dt.isoformat()}T{eh:02d}:{em:02d}:00"
    )

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

# ── A: fallback-estimat (kun når plan.json ikke angiver load) ──
# Hike 0,38 og Walk 0,30 var groft overestimeret: 38 TSS/time for en Z1-gåtur.
# Faktisk målt på Mallorca uge 11: 20,7 TSS/t (3 t bjerghike 12/8) og 9,3 TSS/t
# (rolig hike 13/8). Sat til 0,18/0,12 den 13/8-2026. Rammer kun events der
# bygges herefter — allerede uploadede events beholder deres gamle load.
_LOAD_IF2 = {"Ride":0.45,"VirtualRide":0.45,"Run":0.55,"Swim":0.50,
             "OpenWaterSwim":0.50,"WeightTraining":0.40,"Hike":0.18,"Walk":0.12}

def estimate_load(wo):
    hours = wo.get("moving_time", 3600) / 3600.0
    if2   = _LOAD_IF2.get(wo.get("type"), 0.45)
    return max(round(hours * if2 * 100), 1)

def upload(session, wo, dt):
    if wo is None:
        return None
    # external_id bruges af Intervals til at matche aktiviteter med workouts
    # Format: fas50-YYYY-MM-DD-type (unikt pr. dag og disciplin)
    ext_id = f"fas50-{dt.isoformat()}-{wo['type'].lower()}"

    payload = {
        "name":             wo["name"],
        "type":             wo["type"],
        "start_date_local": f"{dt.isoformat()}T00:00:00",
        "end_date_local":   f"{dt.isoformat()}T23:59:00",
        "moving_time":      wo.get("moving_time", 3600),
        "category":         "WORKOUT",
        "description":      wo.get("description", ""),
        "workout_doc":      wo.get("workout_doc", {}),
        "external_id":      ext_id,
    }

    for attempt in range(3):
        r = session.post(f"{BASE}/events", json=payload)
        if r.status_code in (200, 201):
            body = r.json()
            eid = body.get("id", "?")
            if not body.get("icu_training_load"):
                load = wo.get("load")
                if not isinstance(load, (int, float)) or load <= 0:
                    load = estimate_load(wo)
                session.put(f"{BASE}/events/{eid}", json={"icu_training_load": load})
                print(f"     ↳ load sat: {load}")
            print(f"  ✅ {dt.strftime('%d. %b %a')} — {wo['name']} (id:{eid})")
            start_iso, end_iso = _start_end(wo, dt)
            notify_make("create", event_id=str(eid), payload={
                "subject":    wo["name"],
                "start":      start_iso,
                "end":        end_iso,
                "body":       wo.get("description", ""),
                "location":   "",
                "categories": "Træning"
            })
            return eid
        elif r.status_code == 429:
            print(f"  ⏳ Rate limit — venter 5 sek...")
            time.sleep(5)
        else:
            print(f"  ❌ {dt.strftime('%d. %b %a')} — {r.status_code}: {r.text[:150]}")
            return None
    return None

# ── Main ────────────────────────────────────────────────────────
def run_plan(session, week_filter=0, from_date=None):
    """week_filter>0: kun den uge i det aktive program. week_filter=0: alle dage
    (evt. fra og med from_date — bruges af auto-tilstand på tværs af programmer)."""
    plan     = make_plan()
    days_da  = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]
    ok = skip = err = 0
    cur_week = 0
    posted = {}   # {date: antal POSTede WORKOUT-events}

    # Gruppér plan per dato saa vi kun sletter én gang per dag
    from collections import defaultdict
    by_date = defaultdict(list)
    for dt, wo, note in plan:
        # Uge i det aktive program (u-clampet: dage uden for programmet får
        # uge <1 / >TOTAL_WEEKS og rammes kun af week_filter=0 = alle dage)
        week = _programs.week_no_raw(ACTIVE_PROGRAM, dt)
        if week_filter > 0 and week != week_filter:
            continue
        if from_date and dt < from_date:
            continue
        by_date[dt].append((wo, note, week))

    for dt in sorted(by_date.keys()):
        entries = by_date[dt]
        week = entries[0][2]
        if week != cur_week:
            cur_week = week
            print(f"\n📅 UGE {week} ({dt.strftime('%d. %b')})")
        # Slet eksisterende events for datoen én gang
        delete_existing(session, dt)
        outlook_delete_by_date(dt)
        all_none = all(wo is None for wo, note, _ in entries)
        if all_none:
            print(f"  ⚪ {dt.strftime('%d. %b')} {days_da[dt.weekday()]} — {entries[0][1]}")
            skip += 1
            continue
        for wo, note, _ in entries:
            if wo is None:
                skip += 1
                continue
            eid = upload(session, wo, dt)
            if eid:
                ok += 1
                posted[dt] = posted.get(dt, 0) + 1
            else:
                err += 1
            time.sleep(1.0)

    return ok, skip, err, posted

def verify_uploads(session, posted):
    """GET events på alle uploadede datoer og verificer antal WORKOUT-events matcher."""
    if not posted:
        print("\n⚠️  Ingen uploadede events at verificere.")
        return True

    mismatches = []
    print(f"\n🔍 Verificerer {len(posted)} dato(er) i Intervals.icu...")
    for dt in sorted(posted.keys()):
        expected = posted[dt]
        try:
            r = session.get(f"{BASE}/events", params={
                "oldest": f"{dt.isoformat()}T00:00:00",
                "newest": f"{dt.isoformat()}T23:59:00"
            })
            if r.status_code != 200:
                mismatches.append((dt, expected, f"GET fejlede ({r.status_code})"))
                continue
            events = r.json() if isinstance(r.json(), list) else []
            actual = sum(1 for e in events if e.get("category") == "WORKOUT")
            if actual != expected:
                names = [e.get("name", "?") for e in events if e.get("category") == "WORKOUT"]
                mismatches.append((dt, expected, actual, names))
        except Exception as e:
            mismatches.append((dt, expected, f"exception: {e}"))

    if mismatches:
        print("❌ Verifikation fejlede — mismatch på følgende datoer:")
        for entry in mismatches:
            dt = entry[0]
            exp = entry[1]
            act = entry[2]
            if isinstance(act, int):
                names = entry[3] if len(entry) > 3 else []
                print(f"   {dt.strftime('%d. %b %Y')}: forventet {exp}, fandt {act}"
                      + (f" ({', '.join(names)})" if names else ""))
            else:
                print(f"   {dt.strftime('%d. %b %Y')}: forventet {exp} — {act}")
        return False

    print(f"✅ Verifikation OK — alle {len(posted)} datoer matcher")
    return True


def main():
    import os
    api_key    = os.environ.get("INTERVALS_API_KEY", "")
    week_arg   = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("WEEK_ONLY","0"))

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
    friel_report()

    total_ok = total_skip = total_err = 0
    all_posted = {}  # akkumuleret posted dict på tværs af uger

    if week_arg == -1:
        # Alle dage i plan.json (uanset program)
        print(f"Uploader alle dage i plan.json (aktivt program: {ACTIVE_PROGRAM['id']}, {TOTAL_WEEKS} uger)...")
        ok, skip, err, posted_week = run_plan(session, week_filter=0)
        total_ok += ok; total_skip += skip; total_err += err
        all_posted.update(posted_week)
    elif week_arg == 0:
        # Auto: alle planlagte dage fra og med mandag i denne uge — på tværs af
        # programmer, så søndagskørslen før et programskifte også får det nye
        # programs uge 1 med (var før begrænset til det aktive programs uger).
        monday = date.today() - timedelta(days=date.today().weekday())
        current_week = _programs.week_no(ACTIVE_PROGRAM, date.today())
        print(f"Auto-tilstand ({ACTIVE_PROGRAM['id']} uge {current_week}): uploader alle dage fra {monday}")
        ok, skip, err, posted_week = run_plan(session, week_filter=0, from_date=monday)
        total_ok += ok; total_skip += skip; total_err += err
        all_posted.update(posted_week)
    else:
        # Specifik uge
        ok, skip, err, posted_week = run_plan(session, week_filter=week_arg)
        total_ok += ok; total_skip += skip; total_err += err
        all_posted.update(posted_week)

    print(f"\n{'='*50}")
    print(f"✅ Uploadet:    {total_ok}")
    print(f"⚪ Hvile/rejse: {total_skip}")
    print(f"❌ Fejl:        {total_err}")
    if total_err > 0:
        sys.exit(1)

    verify_ok = verify_uploads(session, all_posted)
    if not verify_ok:
        print("\n❌ Upload-verifikation fejlede — tjek Intervals.icu manuelt.")
        sys.exit(1)

if __name__ == "__main__":
    main()




