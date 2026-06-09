#!/usr/bin/env python3
"""
QA-test: Uploader med absolut pace i description, tom workout_doc.
Tjekker om Intervals auto-genererer korrekt workout_doc.
Kør: python3 test_absolute_pace.py 6x0l12azelkcji76zvktwlbj0
"""
import sys, json, requests
from datetime import date

ATHLETE_ID = "i599466"
BASE       = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
TEST_DATE  = date(2026, 6, 10)

def delete_existing(s):
    r = s.get(f"{BASE}/events", params={
        "oldest": f"{TEST_DATE}T00:00:00",
        "newest": f"{TEST_DATE}T23:59:00"
    })
    for ev in (r.json() if r.ok else []):
        if isinstance(ev, dict) and ev.get("category") == "WORKOUT":
            s.delete(f"{BASE}/events/{ev['id']}")
            print(f"   Slettede: {ev.get('name')}")

def main(key):
    s = requests.Session()
    s.auth = ("API_KEY", key)
    s.headers["Content-Type"] = "application/json"

    print("1. Sletter eksisterende på 10. juni...")
    delete_existing(s)

    # Absolut pace i description — officielt Intervals format
    description = (
        "- Varm-op 10m >5:35/km Pace\n"
        "- Base 30m 4:56-5:34/km Pace\n"
        "- Cool-down 5m >5:35/km Pace"
    )

    payload = {
        "name":             "QA Løb Z2 45 min",
        "type":             "Run",
        "start_date_local": f"{TEST_DATE}T06:00:00",
        "moving_time":      2700,
        "category":         "WORKOUT",
        "description":      description,
        "workout_doc":      {}   # tom — lader Intervals auto-parse
    }

    print("\n2. Uploader med absolut pace i description...")
    r = s.post(f"{BASE}/events", json=payload)
    if not r.ok:
        print(f"FEJL: {r.status_code} — {r.text[:300]}")
        sys.exit(1)

    eid = r.json().get("id")
    print(f"   OK — id: {eid}")

    print("\n3. Fetcher tilbage...")
    ev  = s.get(f"{BASE}/events/{eid}").json()
    doc = ev.get("workout_doc")

    print(f"\n{'='*55}")
    print(f"Description sendt:\n  {description.replace(chr(10), chr(10)+'  ')}")
    print(f"\nworkout_doc gemt af Intervals:")
    print(json.dumps(doc, indent=2, ensure_ascii=False))

    if doc and doc.get("steps"):
        steps = doc["steps"]
        print(f"\n✅ Intervals auto-genererede {len(steps)} steps")
        for i, st in enumerate(steps):
            pace = st.get("pace") or st.get("target") or {}
            print(f"   Trin {i+1}: {st.get('text','?')} — {pace}")
    else:
        print("\n⚠️  workout_doc er stadig tom — Intervals parser ikke automatisk")

    print(f"{'='*55}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
