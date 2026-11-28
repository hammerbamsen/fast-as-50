"""Synk heldags-ugemarkeringer til Outlook (27/11-2026).

Een heldagsbegivenhed pr. programuge med blockType, sted og ugens formaal.
Teksten bygges i scripts/modules/week_marker.py (ren logik, testet); her er
kun Graph-kaldene.

Idempotent: markeringen baerer et fingeraftryk af de felter den viser. Er
fingeraftrykket uaendret, roeres begivenheden ikke. Derfor kan synken koere
dagligt uden at skrive noget.

Env: AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET.
      PROGRAM (valgfri, default det aktive), FROM/TIL (valgfri ISO-datoer),
      DRY_RUN=1 (skriv ingenting, vis kun hvad der ville ske).
"""
import os
import sys
from datetime import date

_REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')
sys.path.insert(0, os.path.join(_REPO_ROOT, 'scripts'))
from modules import week_marker as wm          # noqa: E402
from modules import programs as _programs      # noqa: E402

TIMEOUT = 30
USER = 'kennet@hammerby.com'
GRAPH = f'https://graph.microsoft.com/v1.0/users/{USER}'


def main():
    import requests
    import json as _json

    dry = os.environ.get('DRY_RUN', '').strip() in ('1', 'true', 'yes')
    plan = _json.load(open(os.path.join(_REPO_ROOT, 'data', 'plan.json'), encoding='utf-8'))
    program_id = os.environ.get('PROGRAM', '').strip() or None
    if not program_id:
        prog = _programs.active_program(plan, 'kennet')
        program_id = prog['id'] if prog else None
    # Default: denne uges mandag og fremad. Markeringer paa uger der er forbi
    # er stoej i kalenderen, og de kan ikke aendres alligevel.
    from datetime import timedelta as _td
    i_dag = date.today()
    fra = os.environ.get('FROM', '').strip() or (i_dag - _td(days=i_dag.weekday())).isoformat()
    til = os.environ.get('TIL', '').strip() or None
    uger = wm.plan_weeks(plan, program_id, fra=fra, til=til)
    if not uger:
        print('Ingen uger i vinduet — intet at synke.')
        return 0
    print(f'Program {program_id}: {len(uger)} uger ({uger[0]["start"]} -> {uger[-1]["start"]})'
          + (' [DRY RUN]' if dry else ''))

    token_r = requests.post(
        f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}/oauth2/v2.0/token",
        data={'grant_type': 'client_credentials',
              'client_id': os.environ['AZURE_CLIENT_ID'],
              'client_secret': os.environ['AZURE_CLIENT_SECRET'],
              'scope': 'https://graph.microsoft.com/.default'}, timeout=TIMEOUT)
    token_r.raise_for_status()
    hdrs = {'Authorization': f"Bearer {token_r.json()['access_token']}",
            'Content-Type': 'application/json'}
    hdrs_get = {'Authorization': hdrs['Authorization']}
    print('Token OK')

    # EEN calendarView over hele vinduet — ikke et kald pr. uge.
    from datetime import timedelta
    slut = (date.fromisoformat(uger[-1]['start']) + timedelta(days=8)).isoformat()
    r = requests.get(f'{GRAPH}/calendarView', headers=hdrs_get,
                     params={'startDateTime': f'{uger[0]["start"]}T00:00:00',
                             'endDateTime': f'{slut}T00:00:00',
                             '$select': 'id,subject,categories,isAllDay,start,body',
                             '$top': '400'}, timeout=TIMEOUT)
    if r.status_code != 200:
        print(f'FEJL: calendarView {r.status_code}: {r.text[:200]}')
        return 1
    findes = {}
    for ev in r.json().get('value', []):
        if not wm.er_markering(ev):
            continue
        dag = (ev.get('start') or {}).get('dateTime', '')[:10]
        findes.setdefault(dag, []).append(ev)
    print(f'Fandt {sum(len(v) for v in findes.values())} eksisterende markering(er)')

    uaendret = oprettet = opdateret = fjernet = fejl = 0
    for w in uger:
        onsket = wm.event(w)
        fp = wm.fingerprint(w)
        nuvaerende = findes.pop(w['start'], [])
        # Flere markeringer paa samme mandag: behold den foerste, slet resten.
        for ekstra in nuvaerende[1:]:
            if dry:
                print(f'  [dry] ville slette dublet {ekstra.get("subject")}')
            else:
                requests.delete(f'{GRAPH}/events/{ekstra["id"]}', headers=hdrs_get, timeout=TIMEOUT)
            fjernet += 1
        ev = nuvaerende[0] if nuvaerende else None
        if ev and wm.fingerprint_i_event(ev) == fp:
            uaendret += 1
            continue
        if ev:
            if dry:
                print(f'  [dry] ville opdatere KU{w["start"]}: {onsket["subject"]}')
                opdateret += 1
                continue
            pr = requests.patch(f'{GRAPH}/events/{ev["id"]}', headers=hdrs,
                                json=onsket, timeout=TIMEOUT)
            if pr.status_code in (200, 201):
                opdateret += 1
                print(f'  opdateret {w["start"]}: {onsket["subject"]}')
            else:
                fejl += 1
                print(f'  FEJL patch {w["start"]}: {pr.status_code} {pr.text[:120]}')
        else:
            if dry:
                print(f'  [dry] ville oprette {w["start"]}: {onsket["subject"]}')
                oprettet += 1
                continue
            cr = requests.post(f'{GRAPH}/events', headers=hdrs, json=onsket, timeout=TIMEOUT)
            if cr.status_code in (200, 201):
                oprettet += 1
                print(f'  oprettet {w["start"]}: {onsket["subject"]}')
            else:
                fejl += 1
                print(f'  FEJL opret {w["start"]}: {cr.status_code} {cr.text[:120]}')

    # Markeringer paa mandage der ikke laengere er programuger (fx efter et
    # programskifte) ryddes, saa kalenderen ikke baerer doede uger.
    for dag, evs in findes.items():
        for ev in evs:
            if dry:
                print(f'  [dry] ville fjerne forael­det markering {dag}: {ev.get("subject")}')
            else:
                requests.delete(f'{GRAPH}/events/{ev["id"]}', headers=hdrs_get, timeout=TIMEOUT)
            fjernet += 1

    print(f'Uaendret: {uaendret} · oprettet: {oprettet} · opdateret: {opdateret} '
          f'· fjernet: {fjernet} · fejl: {fejl}')
    return 1 if fejl else 0


if __name__ == '__main__':
    raise SystemExit(main())
