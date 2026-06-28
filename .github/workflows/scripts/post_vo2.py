import os, requests
API_KEY    = os.environ['INTERVALS_API_KEY']
ATHLETE_ID = os.environ['INTERVALS_ATHLETE_ID']
BASE = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH = ('API_KEY', API_KEY)
event = {
    'start_date_local': '2026-06-30T06:30:00',
    'type': 'Run',
    'category': 'WORKOUT',
    'name': 'Løb VO2 5×3 min Z4',
    'description': '- Varm-op 15m >5:35/km Pace\n\n5x\n- Interval 3m 4:13-4:25/km Pace\n- Pause 2m >5:35/km Pace\n\n- Cool-down 10m >5:35/km Pace',
    'moving_time': 3900,
}
r = requests.post(f'{BASE}/events', auth=AUTH, json=event, timeout=30)
print(f'Status: {r.status_code}')
result = r.json()
if isinstance(result, list): print(f'OK: {result[0]["name"]}')
else: print(f'Svar: {result}')
