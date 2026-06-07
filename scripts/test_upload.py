#!/usr/bin/env python3
import sys, requests, json

api_key = sys.argv[1]
athlete_id = "i599466"
BASE = f"https://intervals.icu/api/v1/athlete/{athlete_id}"
session = requests.Session()
session.auth = ("API_KEY", api_key)

# Test 1: Hent athlete info
r = session.get(BASE)
print(f"Athlete: {r.status_code} — {r.text[:100]}")

# Test 2: Hent eksisterende workouts
r2 = session.get(f"{BASE}/workouts", params={"oldest":"2026-06-08","newest":"2026-06-08"})
print(f"Workouts 8.jun: {r2.status_code} — {r2.text[:200]}")

# Test 3: Upload MINIMAL workout uden workout_doc
minimal = {
    "name": "TEST Løb Z2 45 min",
    "type": "Run",
    "start_date_local": "2026-06-09",
    "moving_time": 2700,
    "description": "Test upload"
}
r3 = session.post(f"{BASE}/workouts", json=minimal)
print(f"Upload minimal: {r3.status_code} — {r3.text[:300]}")

# Test 4: Upload med workout_doc
with_doc = {
    "name": "TEST Cykel Z2 60 min",
    "type": "Ride", 
    "start_date_local": "2026-06-10",
    "moving_time": 3600,
    "workout_doc": {"steps": [
        {"type":"step","duration":600,"description":"Z2 warm-up (120-150W)","power":{"value":135,"units":"watts"}},
        {"type":"step","duration":2400,"description":"Z2 steady (150-205W)","power":{"value":177,"units":"watts"}},
        {"type":"step","duration":600,"description":"Z1 cool (100W)","power":{"value":100,"units":"watts"}}
    ]}
}
r4 = session.post(f"{BASE}/workouts", json=with_doc)
print(f"Upload with_doc: {r4.status_code} — {r4.text[:300]}")
