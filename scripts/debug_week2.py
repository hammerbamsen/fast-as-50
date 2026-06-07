import os, json, base64, requests
from datetime import date

API_KEY = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
GH_TOKEN = os.environ.get('GH_TOKEN', '')
REPO = 'hammerbamsen/fast-as-50'
BASE = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH = ('API_KEY', API_KEY)

# Hent uge 2 workouts
r = requests.get(f'{BASE}/workouts', auth=AUTH,
                 params={'oldest': '2026-06-08', 'newest': '2026-06-14'})
print(f"Status: {r.status_code}")
data = r.json()
print(f"Antal workouts: {len(data)}")
for w in data:
    print(f"  {w.get('start_date_local','')[:10]} | {w.get('type')} | {w.get('name')}")

# Gem til debug.json i repo
gh_headers = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github+json'}
# Tjek om debug.json eksisterer
r2 = requests.get(f'https://api.github.com/repos/{REPO}/contents/debug_week2.json', headers=gh_headers)
sha = r2.json().get('sha') if r2.status_code == 200 else None

content = json.dumps({'workouts': data, 'count': len(data)}, indent=2, ensure_ascii=False)
payload = {
    'message': 'debug: uge 2 workouts',
    'content': base64.b64encode(content.encode()).decode(),
}
if sha:
    payload['sha'] = sha

r3 = requests.put(f'https://api.github.com/repos/{REPO}/contents/debug_week2.json',
                  headers=gh_headers, json=payload)
print(f"Gem debug.json: {r3.status_code}")
