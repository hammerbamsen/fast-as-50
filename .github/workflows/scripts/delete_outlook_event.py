import os, requests

CLIENT_ID      = os.environ['AZURE_CLIENT_ID']
TENANT_ID      = os.environ['AZURE_TENANT_ID']
CLIENT_SECRET  = os.environ['AZURE_CLIENT_SECRET']
EVENT_DATE     = os.environ['EVENT_DATE']
SUBJECT_FILTER = os.environ.get('EVENT_SUBJECT', '').strip().lower()
USER           = 'kennet@hammerby.com'
GRAPH          = f'https://graph.microsoft.com/v1.0/users/{USER}'

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

# Hent alle events paa datoen
r = requests.get(
    f'{GRAPH}/calendarView',
    headers=hdrs_get,
    params={'startDateTime': f'{EVENT_DATE}T00:00:00',
            'endDateTime':   f'{EVENT_DATE}T23:59:59',
            '$select': 'id,subject,categories'}
)
events = r.json().get('value', []) if r.status_code == 200 else []
print(f'{EVENT_DATE}: {len(events)} events fundet')
print(f'Filter: "{SUBJECT_FILTER or "alle Traening-events"}"')

deleted = skipped = 0
for e in events:
    subj = e.get('subject', '')
    cats = e.get('categories', [])
    is_training = 'Traening' in cats or 'Træning' in cats

    if is_training and (not SUBJECT_FILTER or SUBJECT_FILTER in subj.lower()):
        dr = requests.delete(f'{GRAPH}/events/{e["id"]}', headers=hdrs)
        if dr.status_code == 204:
            print(f'  Slettet: {subj}')
            deleted += 1
        else:
            print(f'  FEJL: {subj}: {dr.status_code} {dr.text[:100]}')
    else:
        print(f'  Spring over: {subj}')
        skipped += 1

print(f'Slettet: {deleted} | Sprunget over: {skipped}')
