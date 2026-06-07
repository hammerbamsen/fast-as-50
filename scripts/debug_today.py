import os, json, base64, requests
from datetime import date

API_KEY = os.environ["INTERVALS_API_KEY"]
ATHLETE_ID = os.environ["INTERVALS_ATHLETE_ID"]
GH_TOKEN = os.environ["GH_TOKEN"]
REPO = "hammerbamsen/fast-as-50"
BASE = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
AUTH = ("API_KEY", API_KEY)

r = requests.get(f"{BASE}/activities", auth=AUTH,
                 params={"oldest": "2026-06-07", "newest": "2026-06-07"})
acts = r.json() if r.status_code == 200 else []
print(f"Aktiviteter 7. juni: {len(acts)}")
for a in acts:
    print(f"  {a.get('type')} | {a.get('name')} | tss={a.get('training_load')} | id={a.get('id')}")

result = {"date": "2026-06-07", "activities": acts, "status": r.status_code}

gh = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json"}
r2 = requests.get(f"https://api.github.com/repos/{REPO}/contents/debug_today.json", headers=gh)
sha = r2.json().get("sha") if r2.status_code == 200 else None
payload = {"message": "debug: dagens aktiviteter", "content": base64.b64encode(json.dumps(result, indent=2, ensure_ascii=False).encode()).decode()}
if sha: payload["sha"] = sha
requests.put(f"https://api.github.com/repos/{REPO}/contents/debug_today.json", headers=gh, json=payload)
print("Gemt til debug_today.json")
