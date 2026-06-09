#!/usr/bin/env python3
"""
TEST v2: Løb Z2 45 min med absolut pace (sek/km) i stedet for %pace
Formål: få Garmin til at vise "4:56–5:34 min/km" på hvert trin

Kør: python3 test_workout_doc_v2.py 6x0l12azelkcji76zvktwlbj0
"""

import sys, json, requests
from datetime import date

ATHLETE_ID  = "i599466"
BASE        = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
TEST_DATE   = date(2026, 6, 10)

def delete_existing(s, dt):
    r = s.get(f"{BASE}/events", params={
        "oldest": f"{dt}T00:00:00",
        "newest": f"{dt}T23:59:00"
    })
    if r.status_code != 200:
        return
    for ev in r.json():
        if isinstance(ev, dict) and ev.get("category") == "WORKOUT":
            eid = ev.get("id")
            s.delete(f"{BASE}/events/{eid}")
            print(f"   Slettede: {ev.get('name')} (id:{eid})")

def main(api_key):
    s = requests.Session()
    s.auth = ("API_KEY", api_key)
    s.headers["Content-Type"] = "application/json"

    r = s.get(BASE)
    if r.status_code != 200:
        print(f"Forbindelsesfejl: {r.status_code}")
        sys.exit(1)
    print(f"Forbundet: {r.json().get('name')}\n")

    print(f"1. Sletter eksisterende på {TEST_DATE}...")
    delete_existing(s, TEST_DATE)

    # Pace i sek/km — Z1 >5:35 = >335 sek/km, Z2 = 296–334 sek/km
    # start = hurtigste ende, end = langsomste ende
    workout_doc = {
        "steps": [
            {
                "text": "Z1 varm-op (>5:35 min/km)",
                "pace": {"start": 300, "end": 360, "units": "secs/km"},
                "duration": 600
            },
            {
                "text": "Z2 aerob base (4:56–5:34 min/km)",
                "pace": {"start": 296, "end": 334, "units": "secs/km"},
                "duration": 1800
            },
            {
                "text": "Z1 cool-down (>5:35 min/km)",
                "pace": {"start": 300, "end": 360, "units": "secs/km"},
                "duration": 300
            }
        ]
    }

    plain_text = "- 10m Z1 Pace\n- 30m Z2 Pace\n- 5m Z1 Pace"

    payload = {
        "name":             "TEST v2 Løb Z2 45 min",
        "type":             "Run",
        "start_date_local": f"{TEST_DATE}T00:00:00",
        "end_date_local":   f"{TEST_DATE}T23:59:00",
        "moving_time":      45 * 60,
        "category":         "WORKOUT",
        "description":      plain_text,
        "workout_doc":      workout_doc
    }

    print(f"\n2. Uploader TEST v2 til {TEST_DATE}...")
    r = s.post(f"{BASE}/events", json=payload)
    if r.status_code not in (200, 201):
        print(f"FEJL: {r.status_code} — {r.text[:400]}")
        sys.exit(1)

    event_id = r.json().get("id")
    print(f"   OK — event id: {event_id}")

    print(f"\n3. Fetcher tilbage...")
    r = s.get(f"{BASE}/events/{event_id}")
    ev = r.json()
    stored_doc = ev.get("workout_doc")

    print(json.dumps(stored_doc, indent=2, ensure_ascii=False))
    print(f"\nVent 5 min — tjek Garmin Connect-app → ons 10. juni")
    print(f"Viser hvert trin nu pace i min/km?")

if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else ""
    if not key:
        print("Brug: python3 test_workout_doc_v2.py DIN_NOEGLE")
        sys.exit(1)
    main(key)
