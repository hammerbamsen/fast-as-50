#!/usr/bin/env python3
"""
Fast as Fifty — 14-ugers program til Intervals.icu
Datoer verificeret mod Outlook-kalender.

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

import json, sys, time, requests
from datetime import date, timedelta

ATHLETE_ID  = "i599466"
BASE        = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
PLAN_START  = date(2026, 6, 1)
FTP         = 270   # watt
THRESHOLD   = 260   # sek/km = 4:20/km
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
        s_bike(5,  "Z4", "Åbner 5 min"),
        s_bike(5,  "Z1", "Let"),
        s_free(20, "20 MIN ALL-OUT TEST — jævn max-indsats"),
        s_bike_ramp(15, 60, 40, "Cool-down", "cooldown"),
    ])
    return {"name": "FTP-TEST 20 min (opdatér zoner efter)", "type": "Ride",
            "moving_time": 65*60,
            "description": desc + "\n\nEfter testen: nyt FTP = 95% af 20-min snit-watt. Opdatér i Intervals → Settings.",
            "workout_doc": doc}

def run_threshold_test():
    """30-min løbetest — snit-pace for sidste 20 min = ny threshold."""
    desc, doc = build([
        s_run(15, "Z1", "Varm-op"),
        s_reps(3, [s_free(1, "Stride 20 sek"), s_free(1, "Jog 40 sek")]),
        s_free(30, "30 MIN TEST — jævn max-indsats, flad rute"),
        s_run(10, "Z1", "Cool-down"),
    ])
    return {"name": "THRESHOLD-TEST løb 30 min (opdatér pace-zoner efter)", "type": "Run",
            "moving_time": 65*60,
            "description": desc + "\n\nEfter testen: threshold-pace = snit af sidste 20 min. Opdatér zoner i Intervals + config.",
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

    # ── UGE 3: 15-21 jun  BUILD+ (justeret v2 — Formentor) ─────
    # Man: lang løb formiddag (møde kl 13)
    (p+timedelta(14), run_z2_lang(90),        "Lang løb Z2 90 min Mallorca (formiddag)"),
    # Tirs: Formentor — ugens store belastning, 149km
    (p+timedelta(15), bike_formentor(),       "Cykel Formentor 149km"),
    # Ons: aktiv recovery — kun let svøm (hike udgået)
    (p+timedelta(16), swim_let(),             "Svøm let 1500m Mallorca"),
    # Tor: let spin → fly hjem aften
    (p+timedelta(17), bike_z2(60,"Mallorca"), "Cykel let 60 min → fly hjem aften"),
    # Fre: styrke morgen (frisk efter rejse)
    (p+timedelta(18), strength_a(3),          "Styrke A — morgen efter hjemrejse"),
    # Lør: lang løb når udhvilet
    (p+timedelta(19), run_z2_lang(60),        "Lang løb Z2 60 min Gentofte"),
    # Søn: svøm
    (p+timedelta(20), swim_2000(),            "Svøm 2000m"),

    # ── UGE 4: 22-28 jun  RECOVERY (justeret v2 — DK-hverdag) ────
    # Man: svøm før hjemmekontor
    (p+timedelta(21), swim_recovery(30),     "Let svøm 30 min teknik — før hjemmekontor"),
    # Tirs: god formiddag til løb
    (p+timedelta(22), run_z2(45),            "Løb Z2 45 min"),
    # Ons: workshop — kort spin
    (p+timedelta(23), bike_z2(30),           "Let cykel-spin 30 min — workshop dag"),
    # Tor: job fylder formiddag, træning eftermiddag (se TIME_OVERRIDES)
    (p+timedelta(24), bike_z2(45),           "Cykel Z2 45 min — eftermiddag"),
    # Fre: job-fyldt dag — hvile
    (p+timedelta(25), None,                  "Hvile — job-fyldt dag"),
    # Lør: god weekend, lang løb 1,5 time
    (p+timedelta(26), run_z2_lang(90),       "Lang løb Z2 1,5 time"),
    # Søn: styrke (byttet med man svøm)
    (p+timedelta(27), strength_a(3),         "Styrke A Functional Strength 3 sæt"),

    # ── UGE 5: 29 jun–5 jul  BUILD (tir: styrke+løb Z2, tor: styrke A+VO2, fre: svøm 2000m, søn: Hundested) ──
    (p+timedelta(28), swim_let(),            "Svøm 1500m let teknisk"),
    (p+timedelta(29), strength_let(),        "Styrke let 2 sæt recovery"),
    (p+timedelta(29), run_z2(65),            "Løb Z2 65 min"),
    (p+timedelta(30), bike_z2(75),           "Hometrainer Z2 75 min"),
    (p+timedelta(31), strength_a(3),         "Styrke A Functional Strength 3 sæt"),
    (p+timedelta(31), run_vo2_5x3(),         "Løb VO2 5×3 min Z4"),
    (p+timedelta(32), swim_2000(),           "Svøm 2000m teknisk"),
    (p+timedelta(33), run_z2_lang(115),      "Lang løb Z2 115 min"),
    (p+timedelta(34), bike_hundested(),      "Cykel Z2 til Hundested"),

    # ── UGE 6: 6-12 jul  RECOVERY let (Wales ons-søn, tå-hensyn: kun 2 løb) ──
    (p+timedelta(35), ow_swim(40, "Christiansborg-prep"), "OW-svøm 40 min — Christiansborg-prep"),
    (p+timedelta(35), strength_let(),        "Styrke let 2 sæt recovery"),
    (p+timedelta(36), bike_z2(70),           "Cykel Z2 70 min — sidste før Wales"),
    (p+timedelta(37), None,                  "Fly → Wales (ons 8. jul) — hvile/gang"),
    (p+timedelta(38), hike_easy(120),        "Vandring Wales 2 timer — lav intensitet"),
    (p+timedelta(39), run_trail(55, "Trail-løb Z2 Wales"), "Trail-løb Z2 Wales 55 min — TÅ-TEST: stop ved smerte"),
    (p+timedelta(40), hike_easy(90),         "Vandring Wales let / hvile"),
    (p+timedelta(41), run_trail(75, "Trail langtur Z2 Wales"), "Trail langtur Z2 Wales 75 min — kun hvis tåen holdt fredag. Hjemrejse aften"),

    # ── UGE 7: 13-19 jul  BUILD (man-ons Gentofte, tor-søn Mallorca) ──
    (p+timedelta(42), swim_2000(),           "Svøm 2000m — morgen"),
    (p+timedelta(42), strength_a(3),         "Styrke A Functional Strength 3 sæt"),
    (p+timedelta(43), run_vo2_5x3(),         "Løb VO2 5×3 Z4 — ugens stimulus"),
    (p+timedelta(44), bike_z2_z3(80),        "Hometrainer Z2-Z3 80 min"),
    (p+timedelta(45), bike_z2(60,"Mallorca"),"Aktivering cykel Z2 60 min — ankomst Mallorca (tor 16.)"),
    (p+timedelta(46), bike_z2(180,"Mallorca"),"Cykel Z2 lang 3t Mallorca"),
    (p+timedelta(47), bike_z2(240,"Mallorca"),"Cykel Z2 lang 4t Mallorca"),
    (p+timedelta(48), run_z2(60),            "Løb Z2 60 min Mallorca — morgen"),

    # ── UGE 8: 20-26 jul  BUILD+ (Mallorca man-tir, hjem ons 22.) ──
    (p+timedelta(49), bike_sa_calobra(),     "Sa Calobra via Puig Major — tidlig afgang, ugens store fjeld-dag"),
    (p+timedelta(50), bike_z2(210,"Mallorca"),"Cykel Z2 stor dag 3.5t Mallorca"),
    (p+timedelta(51), run_z2_lang(90),       "Lang løb Z2 90 min — formiddag før aftenflyet hjem (ons 22.)"),
    (p+timedelta(52), strength_a(2),         "Styrke let 2 sæt"),
    (p+timedelta(52), run_z2(50),            "Løb Z2 50 min let"),
    (p+timedelta(53), swim_2500(),           "Svøm 2500m"),
    (p+timedelta(54), run_long_km(26, 140),  "Lang løb 26 km — marathon-ladder start"),
    (p+timedelta(55), bike_z2(90),           "Cykel Z2 90 min recovery-spin"),

    # ── UGE 9: 27 jul–2 aug  RECOVERY + RETEST ──────────────────
    (p+timedelta(56), None,                  "Hvile"),
    (p+timedelta(57), swim_let(),            "Svøm let 1500m"),
    (p+timedelta(58), bike_ftp_test(),       "FTP-TEST 20 min — opdatér watt-zoner"),
    (p+timedelta(59), run_threshold_test(),  "THRESHOLD-TEST løb 30 min — opdatér pace-zoner"),
    (p+timedelta(60), None,                  "Musik i Gentofte — hvile (fre 31. jul)"),
    (p+timedelta(61), run_z2(60),            "Løb Z2 60 min let — Musik i Gentofte"),
    (p+timedelta(62), swim_2000(),           "Svøm 2000m — Musik i Gentofte (søn 2. aug)"),

    # ── UGE 10: 3-9 aug  BUILD (fly Mallorca søn 9.) ────────────
    (p+timedelta(63), strength_a(3),         "Styrke A Functional Strength 3 sæt"),
    (p+timedelta(64), run_vo2_4x5(),         "Løb VO2 4×5 Z4-Z5 — nye zoner efter retest"),
    (p+timedelta(65), bike_3x15_z3(90),      "Hometrainer 3×15 Z3"),
    (p+timedelta(66), ow_swim(45),           "OW-svøm 45 min — Christiansborg-prep starter"),
    (p+timedelta(67), run_z2(60),            "Løb Z2 60 min"),
    (p+timedelta(68), run_long_km(29, 155),  "Lang løb 28-30 km — marathon-ladder"),
    (p+timedelta(69), None,                  "Fly → Mallorca #2 (søn 9. aug)"),

    # ── UGE 11: 10-16 aug  BUILD+ Mallorca camp #2 (hjem søn 16.) ──
    (p+timedelta(70), bike_z2(180,"Mallorca"),"Cykel base lang 3t Mallorca"),
    (p+timedelta(71), run_z2(75),            "Løb Z2 75 min Mallorca"),
    (p+timedelta(72), bike_bjerg_z4(),       "Cykel bjerg Z4 Mallorca — VO2 stimulus"),
    (p+timedelta(73), run_z2_lang(120),      "Lang løb Z2 120 min Mallorca"),
    (p+timedelta(74), swim_2000(),           "Svøm 2000m Mallorca (OW hvis muligt)"),
    (p+timedelta(75), bike_z2(210,"Mallorca"),"Cykel Z2 peak 3.5t Mallorca"),
    (p+timedelta(76), None,                  "Hjemrejse Mallorca (søn 16. aug)"),

    # ── UGE 12: 17-23 aug  TAPER (Norge lør 22.) ────────────────
    (p+timedelta(77), ow_swim(45),           "OW-svøm 45 min — Christiansborg-prep"),
    (p+timedelta(78), run_long_km(32, 170),  "Lang løb 32 km — SIDSTE langtur før Médoc"),
    (p+timedelta(79), bike_z2(50),           "Hometrainer Z2 50 min let"),
    (p+timedelta(80), ow_swim(40),           "OW-svøm 40 min — sigtning + startrutine"),
    (p+timedelta(81), run_shakeout(),        "Shakeout løb + strides"),
    (p+timedelta(82), None,                  "Norge start (lør 22. aug)"),
    (p+timedelta(83), run_let(30),           "Let løb Norge (søn 23. aug)"),

    # ── UGE 13: 24-30 aug  TAPER → CHRISTIANSBORG ───────────────
    (p+timedelta(84), None,                  "Hjem fra Norge (man 24. aug)"),
    (p+timedelta(85), ow_swim(30, "Kort tilvænning"), "OW-svøm 30 min — race-tilvænning"),
    (p+timedelta(86), run_shakeout(),        "Løb Z2 + strides"),
    (p+timedelta(87), None,                  "Hvile"),
    (p+timedelta(88), swim_recovery(20),     "Svøm 20 min aktivering — dagen før race"),
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
# Tidspunkt-overrides for dage hvor standardtid (se _start_hour) ikke
# passer med Kennets skema (job/møder/workshop fylder standard-vinduet).
TIME_OVERRIDES = {
    date(2026, 6, 25): (16, 0),   # Tor uge 4 — job fylder formiddag, træning kl 16
}

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
    if dt in TIME_OVERRIDES:
        sh, sm = TIME_OVERRIDES[dt]
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
            eid = r.json().get("id", "?")
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
def run_plan(session, week_filter=0):
    plan     = make_plan()
    days_da  = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]
    ok = skip = err = 0
    cur_week = 0
    posted = {}   # {date: antal POSTede WORKOUT-events}

    # Gruppér plan per dato saa vi kun sletter én gang per dag
    from collections import defaultdict
    by_date = defaultdict(list)
    for dt, wo, note in plan:
        week = (dt - PLAN_START).days // 7 + 1
        if week_filter > 0 and week != week_filter:
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

    total_ok = total_skip = total_err = 0
    all_posted = {}  # akkumuleret posted dict på tværs af uger

    if week_arg == -1:
        # Alle 14 uger
        print("Uploader alle 14 uger...")
        ok, skip, err, posted_week = run_plan(session, week_filter=0)
        total_ok += ok; total_skip += skip; total_err += err
        all_posted.update(posted_week)
    elif week_arg == 0:
        # Auto: fra aktuel uge til 14
        current_week = min(max((date.today() - PLAN_START).days // 7 + 1, 1), 14)
        print(f"Auto-tilstand: uploader uge {current_week}–14")
        for w in range(current_week, 15):
            ok, skip, err, posted_week = run_plan(session, week_filter=w)
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




