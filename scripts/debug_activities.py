import os, json, requests
from datetime import date, timedelta

API_KEY = os.environ.get('INTERVALS_API_KEY','')
ATHLETE_ID = os.environ.get('INTERVALS_ATHLETE_ID','i0')
BASE = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH = ('API_KEY', API_KEY)

today = date.today()
monday = today - timedelta(days=today.weekday())
sunday = monday + timedelta(days=6)

r = requests.get(f'{BASE}/activities', auth=AUTH, params={'oldest': str(monday), 'newest': str(sunday)})
out = {'status': r.status_code, 'count': 0, 'activities': []}
if r.status_code == 200:
    data = r.json()
    out['count'] = len(data)
    for a in data:
        out['activities'].append({
            'date': a.get('start_date_local','')[:10],
            'type': a.get('type'),
            'name': a.get('name'),
            'commute': a.get('commute'),
            'moving_time': a.get('moving_time'),
        })
with open('debug_activities.json','w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
