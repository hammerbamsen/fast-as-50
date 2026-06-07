import requests, json
from collections import defaultdict

s = requests.Session()
s.auth = ("API_KEY", "6x0l12azelkcji76zvktwlbj0")

# Ryd uge 2
r = s.get("https://intervals.icu/api/v1/athlete/i599466/events",
    params={"oldest": "2026-06-08", "newest": "2026-06-14"})
events = [e for e in r.json() if e.get("category") == "WORKOUT"]
print(f"Fandt {len(events)} WORKOUT events i uge 2")

by_day = defaultdict(list)
for e in events:
    by_day[e["start_date_local"][:10]].append(e)

for day, evts in sorted(by_day.items()):
    evts.sort(key=lambda x: x["id"])
    # Behold den med workout_id (struktureret) — ellers behold nyeste
    keep = next((e for e in reversed(evts) if e.get("workout_id")), evts[-1])
    for e in evts:
        if e["id"] != keep["id"]:
            rd = s.delete(f"https://intervals.icu/api/v1/athlete/i599466/events/{e['id']}")
            print(f"  Slettet {e['id']} {day} ({rd.status_code})")
        else:
            print(f"  Beholdt {e['id']} {day} {e['name'][:40]} workout_id={e.get('workout_id')}")

# Tjek workout_doc
print("\nTjekker workout_doc struktur...")
r2 = s.get("https://intervals.icu/api/v1/athlete/i599466/workouts/111")
if r2.status_code == 200:
    w = r2.json()
    print(f"Navn: {w.get('name')}")
    doc = w.get("workout_doc")
    if doc:
        print(f"workout_doc steps: {len(doc.get('steps', []))}")
        print(json.dumps(doc, indent=2)[:400])
    else:
        print("INGEN workout_doc!")
else:
    print(f"Workout 111 fejl: {r2.status_code}")
