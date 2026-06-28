import os, requests
from datetime import date, timedelta

CLIENT_ID     = os.environ['AZURE_CLIENT_ID']
TENANT_ID     = os.environ['AZURE_TENANT_ID']
CLIENT_SECRET = os.environ['AZURE_CLIENT_SECRET']
API_KEY       = os.environ['INTERVALS_API_KEY']
ATHLETE_ID    = os.environ['INTERVALS_ATHLETE_ID']
WEEK          = int(os.environ.get('WEEK', 2))
USER          = 'kennet@hammerby.com'
GRAPH         = f'https://graph.microsoft.com/v1.0/users/{USER}'

# Token
resp = requests.post(
    f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token',
    data={'grant_type':'client_credentials','client_id':CLIENT_ID,
          'client_secret':CLIENT_SECRET,'scope':'https://graph.microsoft.com/.default'}
)
resp.raise_for_status()
token = resp.json()['access_token']
hdrs     = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
hdrs_get = {k:v for k,v in hdrs.items() if k != 'Content-Type'}
print('Azure token OK')

# Datoer
plan_start = date(2026, 6, 1)
week_start = plan_start + timedelta(weeks=WEEK-1)
week_end   = week_start + timedelta(days=6)
print(f'Uge {WEEK}: {week_start} til {week_end}')

# Slet alle Traening-events i perioden
r = requests.get(
    f'{GRAPH}/calendarView',
    headers=hdrs_get,
    params={'startDateTime': f'{week_start}T00:00:00',
            'endDateTime':   f'{week_end}T23:59:59',
            '$select': 'id,subject,categories'}
)
existing = r.json().get('value', []) if r.status_code == 200 else []
deleted = 0
for e in existing:
    if 'Træning' in e.get('categories', []) or 'Træning' in e.get('categories', []):
        dr = requests.delete(f'{GRAPH}/events/{e["id"]}', headers=hdrs)
        status = 'OK' if dr.status_code == 204 else f'FEJL {dr.status_code}'
        print(f'  Slet {status}: {e["subject"]}')
        if dr.status_code == 204:
            deleted += 1
print(f'Slettet: {deleted}')

# Hent workouts fra Intervals
r = requests.get(
    f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events',
    auth=('API_KEY', API_KEY),
    params={'oldest': f'{week_start}T00:00:00', 'newest': f'{week_end}T23:59:00',
            'category': 'WORKOUT'}
)
workouts = r.json() if r.status_code == 200 else []
print(f'{len(workouts)} workouts fra Intervals')

TYPE_EMOJI = {
    'Run': '🏃', 'Ride': '🚴', 'Swim': '🏊',
    'WeightTraining': '💪', 'Walk': '🚶',
}
START_HOUR = {
    'SWIM': (6, 0), 'OW': (6, 0),
    'RUN': (6, 30), 'TRAIL_RUN': (6, 30),
    'RIDE': (7, 0), 'VIRTUAL_RIDE': (7, 0),
    'WEIGHTTRAINING': (7, 0), 'WEIGHT_TRAINING': (7, 0), 'WEIGHTS': (7, 0),
}
TIME_OVERRIDES = {
    '2026-06-25': (16, 0),
}

ok = err = 0
for w in workouts:
    dt    = w.get('start_date_local', '')[:10]
    name  = w.get('name', 'Træning')
    wtype = w.get('type', 'Run')
    dur   = w.get('moving_time', 3600)
    desc  = w.get('description', '')
    emoji = TYPE_EMOJI.get(wtype, '🏋️')

    sh, sm = TIME_OVERRIDES.get(dt, START_HOUR.get(wtype.upper(), (6, 0)))
    end_min = sh * 60 + sm + dur // 60
    eh, em  = end_min // 60, end_min % 60

    event = {
        'subject': f'{emoji} {name}',
        'body': {'contentType': 'text',
                 'content': desc or f'Fast as Fifty - {wtype}'},
        'start': {'dateTime': f'{dt}T{sh:02d}:{sm:02d}:00', 'timeZone': 'Europe/Copenhagen'},
        'end':   {'dateTime': f'{dt}T{eh:02d}:{em:02d}:00', 'timeZone': 'Europe/Copenhagen'},
        'categories': ['Træning'],
        'showAs': 'busy',
        'isReminderOn': True,
        'reminderMinutesBeforeStart': 30,
    }
    resp = requests.post(f'{GRAPH}/events', headers=hdrs, json=event)
    if resp.status_code == 201:
        print(f'  OK {dt} {emoji} {name}')
        ok += 1
    else:
        print(f'  FEJL {dt} {name}: {resp.status_code} {resp.text[:120]}')
        err += 1

print(f'Oprettet: {ok} | Fejl: {err}')
