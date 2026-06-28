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
TIMEOUT       = 30

assert 1 <= WEEK <= 14, f'Ugyldig uge: {WEEK}'

resp = requests.post(
    f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token',
    data={'grant_type':'client_credentials','client_id':CLIENT_ID,
          'client_secret':CLIENT_SECRET,'scope':'https://graph.microsoft.com/.default'},
    timeout=TIMEOUT
)
resp.raise_for_status()
token    = resp.json()['access_token']
hdrs     = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
hdrs_get = {k:v for k,v in hdrs.items() if k != 'Content-Type'}
print('Azure token OK')

plan_start = date(2026, 6, 1)
week_start = plan_start + timedelta(weeks=WEEK-1)
week_end   = week_start + timedelta(days=6)
print(f'Uge {WEEK}: {week_start} til {week_end}')

r = requests.get(
    f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events',
    auth=('API_KEY', API_KEY),
    params={'oldest': f'{week_start}T00:00:00', 'newest': f'{week_end}T23:59:00',
            'category': 'WORKOUT'},
    timeout=TIMEOUT
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

# TRIN 1: Opret nye events FOERST
new_ids = []
ok = err = 0
for w in workouts:
    dt    = w.get('start_date_local', '')[:10]
    name  = w.get('name', 'Træning')
    wtype = w.get('type', 'Run')
    dur   = w.get('moving_time') or 3600  # fallback hvis Intervals mangler moving_time
    desc  = w.get('description', '')
    emoji = TYPE_EMOJI.get(wtype, '🏋')
    sh, sm = START_HOUR.get(wtype.upper(), (6, 0))
    end_min = sh * 60 + sm + dur // 60
    eh, em  = end_min // 60, end_min % 60
    event = {
        'subject': f'{emoji} {name}',
        'body': {'contentType': 'text', 'content': desc or f'Fast as Fifty - {wtype}'},
        'start': {'dateTime': f'{dt}T{sh:02d}:{sm:02d}:00', 'timeZone': 'Europe/Copenhagen'},
        'end':   {'dateTime': f'{dt}T{eh:02d}:{em:02d}:00', 'timeZone': 'Europe/Copenhagen'},
        'categories': ['Træning'],
        'showAs': 'busy',
        'isReminderOn': True,
        'reminderMinutesBeforeStart': 30,
    }
    resp = requests.post(f'{GRAPH}/events', headers=hdrs, json=event, timeout=TIMEOUT)
    if resp.status_code == 201:
        new_ids.append(resp.json()['id'])
        print(f'  Oprettet: {dt} {emoji} {name}')
        ok += 1
    else:
        print(f'  FEJL opret {dt} {name}: {resp.status_code} {resp.text[:120]}')
        err += 1

print(f'Oprettet: {ok} | Fejl: {err}')
if err > 0:
    print('ADVARSEL: Fejl ved oprettelse - springer sletning over for at undgaa tom kalender')
    exit(1)

# TRIN 2: Slet gamle Traening-events med pagination
url    = f'{GRAPH}/calendarView'
params = {
    'startDateTime': f'{week_start}T00:00:00',
    'endDateTime':   f'{week_end}T23:59:59',
    '$select': 'id,subject,categories',
    '$top': '50',
}
existing = []
while url:
    r = requests.get(url, headers=hdrs_get, params=params, timeout=TIMEOUT)
    params = None
    body   = r.json()
    existing.extend(body.get('value', []))
    url = body.get('@odata.nextLink')

print(f'Fandt {len(existing)} eksisterende events')
deleted = 0
for e in existing:
    if e['id'] in new_ids:
        continue
    cats = e.get('categories', [])
    if any(c in ('Træning', 'Traening') for c in cats):
        dr = requests.delete(f'{GRAPH}/events/{e["id"]}', headers=hdrs, timeout=TIMEOUT)
        if dr.status_code in (204, 404):
            print(f'  Slettet: {e["subject"]}')
            deleted += 1
        else:
            print(f'  FEJL slet {e["subject"]}: {dr.status_code}')

print(f'Slettet: {deleted} gamle events')
print('DONE')
