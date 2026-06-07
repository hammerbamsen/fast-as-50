#!/usr/bin/env python3
import os, requests, json
from datetime import date, timedelta

API_KEY    = os.environ["INTERVALS_API_KEY"]
ATHLETE_ID = os.environ["INTERVALS_ATHLETE_ID"]
BASE       = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
AUTH       = ("API_KEY", API_KEY)

oldest = str(date.today() - timedelta(days=3))
newest = str(date.today())
r = requests.get(f"{BASE}/wellness", auth=AUTH, params={"oldest": oldest, "newest": newest})
print("HTTP:", r.status_code)
data = r.json()
for d in data:
    # Print kun relevante felter
    keys = [k for k in d.keys() if d[k] is not None]
    print(d.get("date",""), {k: d[k] for k in keys if k not in ["id","athlete_id"]})
