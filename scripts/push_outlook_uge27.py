"""
Push uge 27 træningsevents fra Intervals til Outlook.
Læser præcis hvad der er i Intervals — ingen hardkodede workouts.
Kør: python3 push_outlook_uge27.py
Kræver AZURE_CLIENT_SECRET i miljø (sat i ~/.zshrc)
"""
import os, sys, json, requests
from datetime import datetime, timedelta

# Azure / Graph
AZURE_CLIENT  = "d6cc8ce4-b681-4b87-8873-5d302b91f8bf"
AZURE_TENANT  = "003c17d1-406c-4f3a-ba81-5ac09bf49036"
GRAPH_BASE    = "https://graph.microsoft.com/v1.0"
OUTLOOK_CAL   = "kennet@hammerby.com"

# Intervals
INTERVALS_KEY = "6x0l12azelkcji76zvktwlbj0"
ATHLETE_ID    = "i599466"

# Sport → emoji
EMOJI = {
    "Swim": "🏊",
    "Run": "🏃",
    "Ride": "🚴",
    "WeightTraining": "💪",
    "Hike": "⛰️",
}

def get_token():
    secret = os.environ.get("AZURE_CLIENT_SECRET", "")
    if not secret:
        print("❌ AZURE_CLIENT_SECRET ikke sat — tjek ~/.zshrc")
        sys.exit(1)
    r = requests.post(
        f"https://login.microsoftonline.com/{AZURE_TENANT}/oauth2/v2.0/token",
        data={
            "client_id": AZURE_CLIENT,
            "client_secret": secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
    )
    if r.status_code != 200:
        print(f"❌ Token fejl: {r.status_code} {r.text[:100]}")
        sys.exit(1)
    token = r.json()["access_token"]
    print("✅ Graph token hentet")
    return token

def delete_existing(token, date_str):
    """Slet alle Træning-events på dato."""
    start = f"{date_str}T00:00:00"
    end   = f"{date_str}T23:59:59"
    r = requests.get(
        f"{GRAPH_BASE}/users/{OUTLOOK_CAL}/calendarView",
        headers={"Authorization": f"Bearer {token}"},
        params={"startDateTime": start, "endDateTime": end,
                "$select": "id,subject,categories", "$top": "50"}
    )
    events = r.json().get("value", [])
    deleted = 0
    for ev in events:
        if "Træning" in ev.get("categories", []):
            requests.delete(
                f"{GRAPH_BASE}/users/{OUTLOOK_CAL}/events/{ev['id']}",
                headers={"Authorization": f"Bearer {token}"}
            )
            deleted += 1
    if deleted:
        print(f"  🗑️  Slettet {deleted} eksisterende event(s) på {date_str}")

def create_event(token, date_str, name, workout_type, duration_min):
    """Opret Outlook-event."""
    emoji = EMOJI.get(workout_type, "🏋️")
    
    # Starttider per sport
    start_hours = {
        "Swim": 7, "Run": 7, "Ride": 8,
        "WeightTraining": 7, "Hike": 9
    }
    start_h = start_hours.get(workout_type, 7)
    
    start_dt = f"{date_str}T{start_h:02d}:00:00"
    end_hour = start_h + duration_min // 60
    end_min  = duration_min % 60
    end_dt   = f"{date_str}T{end_hour:02d}:{end_min:02d}:00"

    payload = {
        "subject": f"{emoji} {name}",
        "start": {"dateTime": start_dt, "timeZone": "Europe/Copenhagen"},
        "end":   {"dateTime": end_dt,   "timeZone": "Europe/Copenhagen"},
        "categories": ["Træning"],
        "showAs": "busy",
        "isReminderOn": True,
        "reminderMinutesBeforeStart": 30,
        "body": {
            "contentType": "text",
            "content": f"Fast as Fifty — Uge 27\n{name}\nVarighed: {duration_min} min"
        }
    }
    r = requests.post(
        f"{GRAPH_BASE}/users/{OUTLOOK_CAL}/events",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload
    )
    if r.status_code in (200, 201):
        print(f"  📅 Oprettet: {emoji} {name} ({date_str} {start_h:02d}:00, {duration_min} min)")
    else:
        print(f"  ❌ Fejl {r.status_code}: {r.text[:120]}")

def fetch_intervals_events():
    """Hent uge 27 events fra Intervals."""
    r = requests.get(
        f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events",
        auth=("API_KEY", INTERVALS_KEY),
        params={"oldest": "2026-06-28", "newest": "2026-07-05"}
    )
    return r.json()

def main():
    print("🚀 Push uge 27 til Outlook\n")
    token = get_token()

    print("\n📥 Henter events fra Intervals...")
    events = fetch_intervals_events()
    print(f"   Fandt {len(events)} events\n")

    # Saml unikke datoer og slet eksisterende
    dates = set(e["start_date_local"][:10] for e in events)
    print("🗑️  Rydder eksisterende Træning-events...")
    for d in sorted(dates):
        delete_existing(token, d)

    print("\n📅 Opretter events i Outlook...")
    for e in events:
        date_str     = e["start_date_local"][:10]
        name         = e.get("name", "Træning")
        workout_type = e.get("type", "Workout")
        duration_min = (e.get("moving_time") or 0) // 60
        if duration_min == 0:
            duration_min = 60  # fallback

        create_event(token, date_str, name, workout_type, duration_min)

    print("\n✅ Færdig — uge 27 ligger nu i Outlook")

if __name__ == "__main__":
    main()
