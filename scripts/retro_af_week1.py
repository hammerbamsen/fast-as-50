import os, requests
from datetime import date, timedelta

API_KEY = os.environ["INTERVALS_API_KEY"]
ATHLETE_ID = os.environ["INTERVALS_ATHLETE_ID"]
AUTH = ("API_KEY", API_KEY)
BASE = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"

# Uge 1: 1-7 juni 2026 — alle 7 dage var AF-dage (Alkohol=0)
week1_dates = [date(2026, 6, 1) + timedelta(days=i) for i in range(7)]

for d in week1_dates:
    r = requests.put(
        f"{BASE}/wellness/{d.isoformat()}",
        auth=AUTH,
        headers={"Content-Type": "application/json"},
        json={"Alkohol": 0}
    )
    print(f"  {d} → {r.status_code}: {r.text[:80]}")

print("Done — 7/7 AF-dage sat i Intervals")
