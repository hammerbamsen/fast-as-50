#!/usr/bin/env python3
import os, requests, json
from datetime import date, timedelta
import subprocess, base64, urllib.request

API_KEY    = os.environ["INTERVALS_API_KEY"]
ATHLETE_ID = os.environ["INTERVALS_ATHLETE_ID"]
GH_TOKEN   = os.environ["GH_TOKEN"]
BASE       = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
AUTH       = ("API_KEY", API_KEY)

oldest = str(date.today() - timedelta(days=3))
newest = str(date.today())
r = requests.get(f"{BASE}/wellness", auth=AUTH, params={"oldest": oldest, "newest": newest})
output = f"HTTP: {r.status_code}
"
data = r.json()
for d in data:
    output += json.dumps(d) + "
"

print(output)

# Skriv til debug_output.txt i repoen
import urllib.request as ur
# Hent SHA
try:
    req = ur.Request(
        "https://api.github.com/repos/hammerbamsen/fast-as-50/contents/debug_output.txt",
        headers={"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    )
    with ur.urlopen(req) as resp:
        sha = json.load(resp)["sha"]
except: sha = None

payload = {"message": "debug output", "content": base64.b64encode(output.encode()).decode()}
if sha: payload["sha"] = sha

req2 = ur.Request(
    "https://api.github.com/repos/hammerbamsen/fast-as-50/contents/debug_output.txt",
    data=json.dumps(payload).encode(), method="PUT",
    headers={"Authorization": f"token {GH_TOKEN}", "Content-Type": "application/json"}
)
with ur.urlopen(req2) as resp:
    print("Skrevet til debug_output.txt, status:", resp.status)
