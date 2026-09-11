#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plan-indbakke i Outlook (blok 16, 11/9-2026).

Formål: Claude skal kunne ændre planen fra chatten uden Mac, push eller
Worker. Cowork-sessionen kan ikke nå GitHub eller Worker'en (proxy), men den
kan skrive i Kennets Outlook-kalender via Microsoft 365-connectoren. Så:

  Claude opretter et kalender-event den 1/1-2030 kl. 12:00 (parkeringsdato, showAs
  free) med subject 'FAF-INBOX <forslag-id>' og hele plan-edit-payload'en
  som base64-JSON i body'en. Dette script (cron + manuelt) henter events
  på parkeringsdatoen, kører hver payload gennem scripts/apply_edit.py —
  NØJAGTIG samme vej som Plan-fanen og Worker'en (gate, plan.json-commit,
  Intervals + Outlook for berørte datoer, Martin-signal) — og sletter
  eventet ved succes. Afvises forslaget, omdøbes eventet til
  'FAF-INBOX-AFVIST …' og bliver stående, så det kan ses i kalenderen.

Payload-format i body (base64 af UTF-8 JSON):
  {"requestId": "...", "action": "apply_proposal", "entryId": "proposal:<id>",
   "params": {"proposal": {...}}, "confirmedWarn": true, "athlete": "kennet"}
Alle plan-edit-actions er tilladt (move, adjust, set_zones …) — det er den
samme payload som Worker'en dispatcher.

Kræver: AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET (Calendars.ReadWrite, samme
app som Outlook-synken), GITHUB_TOKEN, INTERVALS_API_KEY.
"""
import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

import requests

USER = 'kennet@hammerby.com'
GRAPH = f'https://graph.microsoft.com/v1.0/users/{USER}'
PARK_DAY = os.environ.get('FAF_INBOX_DAY', '2030-01-01')
PREFIX = 'FAF-INBOX '
PREFIX_FAIL = 'FAF-INBOX-AFVIST '
TIMEOUT = 30
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def graph_token():
    r = requests.post(
        f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}/oauth2/v2.0/token",
        data={'grant_type': 'client_credentials', 'client_id': os.environ['AZURE_CLIENT_ID'],
              'client_secret': os.environ['AZURE_CLIENT_SECRET'],
              'scope': 'https://graph.microsoft.com/.default'},
        timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()['access_token']


def list_inbox(hdrs):
    url = f'{GRAPH}/calendarView'
    # calendarView tolker start/end som UTC; parkeringsdatoen er lokal tid
    # (første kørsel 11/9 fandt 0 events fordi 00:00 CET = 23:00Z dagen før).
    # Derfor ±1 dag — det er alligevel kun FAF-INBOX-subjects der tælles.
    from datetime import date as _d, timedelta as _td
    pd = _d.fromisoformat(PARK_DAY)
    params = {'startDateTime': f'{pd - _td(days=1)}T00:00:00', 'endDateTime': f'{pd + _td(days=1)}T23:59:59',
              '$select': 'id,subject,body,createdDateTime', '$top': '50'}
    out = []
    while url:
        r = requests.get(url, headers=hdrs, params=params, timeout=TIMEOUT)
        params = None
        r.raise_for_status()
        body = r.json()
        out.extend(e for e in body.get('value', []) if (e.get('subject') or '').startswith(PREFIX))
        url = body.get('@odata.nextLink')
    out.sort(key=lambda e: e.get('createdDateTime') or '')
    return out


def decode_payload(ev):
    """Body er text eller html; hiv base64-blokken ud og dekod."""
    raw = ((ev.get('body') or {}).get('content') or '')
    raw = re.sub(r'<[^>]+>', ' ', raw)                     # html → tekst
    raw = raw.replace('&nbsp;', ' ').replace('&amp;', '&')
    m = re.search(r'([A-Za-z0-9+/=]{40,})', raw.replace('\n', '').replace('\r', '').replace(' ', ''))
    if not m:
        raise ValueError('ingen base64-payload i body')
    data = base64.b64decode(m.group(1)).decode('utf-8')
    payload = json.loads(data)
    for k in ('action', 'entryId'):
        if not payload.get(k):
            raise ValueError(f'payload mangler {k}')
    payload.setdefault('requestId', 'inbox-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    payload.setdefault('athlete', 'kennet')
    return payload


def run_apply(payload):
    """Kør apply_edit.py som subprocess med payload'en som GH_EVENT_PAYLOAD."""
    env = dict(os.environ)
    env['GH_EVENT_PAYLOAD'] = json.dumps({'client_payload': payload}, ensure_ascii=False)
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'apply_edit.py')],
                       env=env, cwd=ROOT, capture_output=True, text=True)
    print(p.stdout[-4000:])
    if p.stderr:
        print(p.stderr[-2000:])
    return p.returncode


def fetch_result(request_id):
    """Læs data/edit_result.json fra GitHub (apply_edit skriver via Contents API)."""
    r = requests.get(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/contents/data/edit_result.json",
                     headers={'Authorization': f"Bearer {os.environ['GITHUB_TOKEN']}",
                              'Accept': 'application/vnd.github.raw+json'}, timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    try:
        return r.json().get(request_id)
    except Exception:
        return None


def main():
    token = graph_token()
    hdrs = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    events = list_inbox(hdrs)
    print(f'Indbakke {PARK_DAY}: {len(events)} forslag')
    failed = 0
    for ev in events:
        subj = ev.get('subject', '')
        print(f'--- {subj}')
        try:
            payload = decode_payload(ev)
        except Exception as ex:
            print(f'  FEJL payload: {ex}')
            requests.patch(f"{GRAPH}/events/{ev['id']}", headers=hdrs,
                           json={'subject': PREFIX_FAIL + subj[len(PREFIX):] + f' (payload: {ex})'[:200]},
                           timeout=TIMEOUT)
            failed += 1
            continue
        rc = run_apply(payload)
        res = fetch_result(payload['requestId']) or {}
        status = res.get('status')
        print(f"  apply_edit rc={rc} status={status} gate={(res.get('gate') or {}).get('msg')}")
        if rc == 0 and status == 'ok':
            requests.delete(f"{GRAPH}/events/{ev['id']}", headers=hdrs, timeout=TIMEOUT)
            print('  ✅ anvendt — event slettet')
            if res.get('sync_errors'):
                print(f"  ⚠️ sync_errors: {res['sync_errors']}")
        else:
            msg = ((res.get('gate') or {}).get('msg') or res.get('error') or f'rc={rc}')
            requests.patch(f"{GRAPH}/events/{ev['id']}", headers=hdrs,
                           json={'subject': (PREFIX_FAIL + subj[len(PREFIX):] + ' — ' + str(msg))[:250]},
                           timeout=TIMEOUT)
            print(f'  ❌ ikke anvendt: {msg}')
            failed += 1
    if failed:
        raise SystemExit(1)
    print('DONE')


if __name__ == '__main__':
    main()
