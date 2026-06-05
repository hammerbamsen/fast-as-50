#!/usr/bin/env python3
"""
Fast as Fifty — TrainingPeaks workout push
Pusher planlagte workouts til TrainingPeaks via cookie-auth.
Køres manuelt som del af søndagsritualet via workflow_dispatch.
"""
import os, json, requests
from datetime import date, timedelta

TP_COOKIE   = os.environ.get("TP_AUTH_COOKIE", "")
ATHLETE_ID  = os.environ.get("TP_ATHLETE_ID", "")
TP_BASE     = "https://tpapi.trainingpeaks.com"
HEADERS     = {
    "Cookie":       f"Production_tpAuth={TP_COOKIE}",
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "User-Agent":   "Mozilla/5.0"
}

# Træningszoner
RUN_THRESHOLD_SEC_PER_KM = 260  # 4:20/km
RUN_ZONES = {
    "Z1": (0, 296),
    "Z2": (296, 334),
    "Z3": (265, 295),
    "Z4": (253, 265),
    "Z5": (233, 252),
}
FTP_WATTS = 270
BIKE_ZONES = {
    "Z1": (0, 149),
    "Z2": (150, 205),
    "Z3": (205, 245),
    "Z4": (245, 285),
    "Z5": (285, 325),
}

def get_athlete_id():
    """Hent athlete ID fra TP"""
    print(f"Kalder: {TP_BASE}/users/v3/user")
    r = requests.get(f"{TP_BASE}/users/v3/user", headers=HEADERS)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
    if r.status_code == 200:
        data = r.json()
        # TrainingPeaks returnerer {"user": {"userId": 2508481, ...}}
        pid = (data.get("user") or {}).get("userId") or               data.get("userId") or data.get("personId") or data.get("id")
        print(f"Athlete ID: {pid}")
        return str(pid) if pid else None
    return None

def push_workout(athlete_id, workout_date, title, description, workout_type, tss, duration_mins, structure=None):
    """Push en workout til TrainingPeaks"""
    payload = {
        "athleteId":     athlete_id,
        "workoutDay":    workout_date,
        "title":         title,
        "description":   description,
        "workoutType":   workout_type,  # "Run", "Bike", "Swim", "Strength"
        "totalTimePlanned": duration_mins * 60,
        "tssPlanned":    tss,
        "ifPlanned":     0.75,
    }
    r = requests.post(
        f"{TP_BASE}/fitness/v6/athletes/{athlete_id}/workouts",
        headers=HEADERS,
        json=payload
    )
    print(f"  Workout response: {r.status_code} {r.text[:200] if r.status_code not in [200,201] else 'OK'}")
    if r.status_code in [200, 201]:
        print(f"  ✓ {title} ({workout_date})")
        return r.json()
    else:
        print(f"  ✗ {title} fejl {r.status_code}: {r.text[:200]}")
        return None

def next_monday():
    today = date.today()
    days_ahead = 7 - today.weekday()
    if days_ahead == 7: days_ahead = 0
    return today + timedelta(days=days_ahead)

def main():
    print("Forbinder til TrainingPeaks...")
    athlete_id = get_athlete_id()
    if not athlete_id:
        print("Kunne ikke hente athlete ID — tjek cookie")
        return
    print(f"Athlete ID: {athlete_id}")

    mon = next_monday()
    print(f"\nPusher uge {mon} → {mon + timedelta(days=6)}")

    # Hent planlagte sessioner fra data.json (sættes af søndagsritualet)
    try:
        r = requests.get("https://raw.githubusercontent.com/hammerbamsen/fast-as-50/main/data.json")
        data = r.json()
        sessions = data.get("week_sessions", [])
        week_no = data.get("meta", {}).get("week", 1)
    except:
        sessions = []
        week_no = 1

    # Byg workouts baseret på sessioner
    workouts_pushed = 0
    for i, s in enumerate(sessions):
        workout_date = str(mon + timedelta(days=i))
        disc = s.get("disc", "free")
        label = s.get("label", "Træning")

        if disc == "run":
            desc = build_run_description(label, week_no)
            push_workout(athlete_id, workout_date, label, desc, "Run", tss=60, duration_mins=60)
            workouts_pushed += 1
        elif disc == "bike":
            desc = build_bike_description(label, week_no)
            push_workout(athlete_id, workout_date, label, desc, "Bike", tss=70, duration_mins=75)
            workouts_pushed += 1
        elif disc == "strength":
            push_workout(athlete_id, workout_date, label,
                "Functional Strength 2: Thruster, Renegade Row, Push-Up, KB Swing, RDL, Bulgarian Split Squat",
                "Strength", tss=40, duration_mins=45)
            workouts_pushed += 1
        elif disc == "swim":
            push_workout(athlete_id, workout_date, label,
                "2000m tekniktræning. 400m opvarmning → 6×100m fokus → 400m afvikling.",
                "Swim", tss=50, duration_mins=50)
            workouts_pushed += 1

    print(f"\n{workouts_pushed} workouts pushet til TrainingPeaks ✓")
    print("Synker til Garmin automatisk inden for 15 min.")

def build_run_description(label, week_no):
    if "Z2" in label or "easy" in label.lower() or "lang" in label.lower():
        return (
            f"Z2 løb — aerob base\n"
            f"Pace: 4:56-5:34 /km\n"
            f"HR: holdes under tærsklen\n"
            f"Fokus: næsetrækning, afslappet kadence ~175 spm"
        )
    elif "Z3" in label or "tempo" in label.lower():
        return (
            f"Tempo løb\n"
            f"Opvarmning 10 min Z2 → 20 min Z3 (4:26-4:55/km) → 10 min Z2\n"
            f"Fokus: kontrolleret ubehag, jævnt effort"
        )
    elif "interval" in label.lower() or "Z4" in label or "Z5" in label:
        return (
            f"Intervalløb\n"
            f"Opvarmning 10 min Z2\n"
            f"4×8 min Z4 @ 4:13-4:25/km / 3 min Z1 recovery\n"
            f"Cool-down 10 min Z2"
        )
    return f"Løb — {label}\nPace efter fornemmelse. Threshold: 4:20/km"

def build_bike_description(label, week_no):
    if "Z2" in label or "aerob" in label.lower():
        return (
            f"Z2 cykling — aerob base\n"
            f"Watt: 150-205W (FTP {FTP_WATTS}W)\n"
            f"Fokus: jævn kadence 85-95 rpm"
        )
    elif "Z3" in label or "5×3" in label or "interval" in label.lower():
        return (
            f"Cykel intervaller\n"
            f"Opvarmning 10 min Z2 (150-205W)\n"
            f"5×3 min Z3 @ 205-245W / 2 min Z1 recovery\n"
            f"Cool-down 10 min Z2\n"
            f"Fokus: høj kadence 90+ rpm i intervallerne"
        )
    elif "Z4" in label or "threshold" in label.lower():
        return (
            f"Threshold cykling\n"
            f"Opvarmning 10 min Z2\n"
            f"2×20 min Z4 @ 245-285W / 5 min Z1\n"
            f"Cool-down 10 min\n"
            f"FTP: {FTP_WATTS}W"
        )
    return f"Cykling — {label}\nFTP: {FTP_WATTS}W. Kør efter plan."

if __name__ == "__main__":
    main()
