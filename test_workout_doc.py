#!/usr/bin/env python3
"""
TEST: Løb Z2 45 min — 10. juni 2026
Uploader med korrekt workout_doc format og fetcher tilbage for at se hvad Intervals gemmer.
Formålet: verificere at Garmin viser strukturerede trin (opvarmning / Z2 / cool-down).

Kør i terminalen:
  cd ~/projekter/fast-as-fifty
  python3 test_workout_doc.py DIN_API_NOEGLE

Find din API-nøgle på: intervals.icu → Settings → Developer Settings
"""

import sys, json, requests
from datetime import date

ATHLETE_ID  = "i599466"
BASE        = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
TEST_DATE   = date(2026, 6, 10)   # Onsdag — "Løb Z2 45 min tidlig"

# ── Zone-konstanter (%pace — threshold = 4:20/km = 260 sek/km) ──
# Lavere % = langsommere = Z1/Z2.  Højere % = hurtigere = Z4/Z5.
Z1_PACE = {"start": 65, "end": 78,  "units": "%pace"}   # >5:35/km
Z2_PACE = {"start": 78, "end": 88,  "units": "%pace"}   # 4:56–5:34/km
Z3_PACE = {"start": 88, "end": 98,  "units": "%pace"}   # 4:26–4:55/km
Z4_PACE = {"start": 98, "end": 103, "units": "%pace"}   # 4:13–4:25/km
Z5_PACE = {"start": 103,"end": 112, "units": "%pace"}   # 3:53–4:12/km


def delete_existing(s, dt):
    r = s.get(f"{BASE}/events", params={
        "oldest": f"{dt}T00:00:00",
        "newest": f"{dt}T23:59:00"
    })
    if r.status_code != 200:
        print(f"   ⚠️  Kan ikke hente events: {r.status_code}")
        return
    deleted = 0
    for ev in r.json():
        if isinstance(ev, dict) and ev.get("category") == "WORKOUT":
            eid = ev.get("id")
            rd = s.delete(f"{BASE}/events/{eid}")
            if rd.status_code in (200, 204):
                print(f"   🗑️  Slettede: '{ev.get('name','?')}' (id:{eid})")
                deleted += 1
    if deleted == 0:
        print("   (ingen eksisterende workouts at slette)")


def main(api_key):
    s = requests.Session()
    s.auth = ("API_KEY", api_key)
    s.headers["Content-Type"] = "application/json"

    # Tjek forbindelse
    r = s.get(BASE)
    if r.status_code != 200:
        print(f"❌ Forbindelsesfejl: {r.status_code} — {r.text[:200]}")
        sys.exit(1)
    print(f"✅ Forbundet: {r.json().get('name', ATHLETE_ID)}\n")

    # ── STEP 1: Slet eksisterende ──────────────────────────────
    print(f"1. Sletter eksisterende workouts på {TEST_DATE}...")
    delete_existing(s, TEST_DATE)

    # ── STEP 2: Byg payload med korrekt workout_doc ────────────
    # run_z2(45): 10m Z1 varm-op + 30m Z2 base + 5m Z1 cool
    plain_text = (
        "- 10m Z1 Pace\n"
        "- 30m Z2 Pace\n"
        "- 5m Z1 Pace"
    )

    workout_doc = {
        "steps": [
            {
                "text": "Z1 varm-op",
                "pace": Z1_PACE,
                "duration": 600          # 10 min
            },
            {
                "text": "Z2 aerob base",
                "pace": Z2_PACE,
                "duration": 1800         # 30 min
            },
            {
                "text": "Z1 cool-down",
                "pace": Z1_PACE,
                "duration": 300          # 5 min
            }
        ]
    }

    payload = {
        "name":             "TEST Løb Z2 45 min",
        "type":             "Run",
        "start_date_local": f"{TEST_DATE}T00:00:00",
        "end_date_local":   f"{TEST_DATE}T23:59:00",
        "moving_time":      45 * 60,
        "category":         "WORKOUT",
        "description":      plain_text,
        "workout_doc":      workout_doc
    }

    # ── STEP 3: Upload ─────────────────────────────────────────
    print(f"\n2. Uploader TEST workout til {TEST_DATE}...")
    r = s.post(f"{BASE}/events", json=payload)
    if r.status_code not in (200, 201):
        print(f"❌ FEJL: {r.status_code} — {r.text[:400]}")
        sys.exit(1)

    event_id = r.json().get("id")
    print(f"   ✅ Uploadet — event id: {event_id}")

    # ── STEP 4: Fetch tilbage og inspicér ─────────────────────
    print(f"\n3. Fetcher event {event_id} tilbage fra Intervals...")
    r = s.get(f"{BASE}/events/{event_id}")
    if r.status_code != 200:
        print(f"❌ Kan ikke fetche: {r.status_code}")
        sys.exit(1)

    ev          = r.json()
    stored_doc  = ev.get("workout_doc")
    stored_desc = ev.get("description", "")

    print(f"\n{'='*55}")
    print(f"NAVN:        {ev.get('name')}")
    print(f"TYPE:        {ev.get('type')}")
    print(f"\nDESCRIPTION (plain text):")
    print(f"  {stored_desc}")
    print(f"\nWORKOUT_DOC (JSON — hvad Garmin bruger):")
    print(json.dumps(stored_doc, indent=2, ensure_ascii=False))

    # ── STEP 5: Konklusion ────────────────────────────────────
    print(f"\n{'='*55}")
    if stored_doc and stored_doc.get("steps"):
        n = len(stored_doc["steps"])
        print(f"✅ GODT: workout_doc har {n} steps gemt i Intervals.")
        print(f"   Garmin BØR vise strukturerede trin på uret.")
    else:
        print(f"⚠️  workout_doc er TOM — Intervals gemte den ikke.")
        print(f"   Vi skal bruge et andet format (f.eks. ZWO-fil).")

    print(f"\nNæste skridt:")
    print(f"  1. Vent 5–10 min (Garmin synker automatisk)")
    print(f"  2. Garmin Connect-app → Kalender → ons 10. juni")
    print(f"  3. Tjek om workout har 3 trin: varm-op / Z2 / cool-down")
    print(f"\n  Intervals: https://intervals.icu/calendar")
    print(f"  Event id:  {event_id}")
    print(f"{'='*55}")


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else ""
    if not key:
        print("Brug: python3 test_workout_doc.py DIN_API_NOEGLE")
        print("Find din nøgle: intervals.icu → Settings → Developer Settings")
        sys.exit(1)
    main(key)
