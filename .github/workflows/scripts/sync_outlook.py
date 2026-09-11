import os
import sys
from datetime import date, timedelta

# Tidslogikken (styrke 06:30, +15 min, aldrig overlap) ligger i
# scripts/modules/outlook_times.py — samme kilde som plan-edit (apply_edit.py).
_REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')
sys.path.insert(0, os.path.join(_REPO_ROOT, 'scripts'))
from modules.outlook_times import schedule_day, event_body, normalize_overrides  # noqa: E402

# ── Synk (kræver env + netværk) ───────────────────────────────────────────────

def _load_time_overrides(repo_root):
    """Tidspunkt-overrides fra plan.json — SAMME kilde som build_workouts.py.
    Uden dette havde dette script sin egen tidstabel, og et pas flyttet til
    eftermiddagen i plan.json landede alligevel 06:30 i kalenderen (28/7-2026)."""
    import json as _json
    for p in ('data/plan.json', os.path.join(repo_root, 'data', 'plan.json')):
        try:
            with open(p, encoding='utf-8') as f:
                raw = _json.load(f)['athletes']['kennet'].get('timeOverrides', {})
        except Exception:
            continue
        out = normalize_overrides(raw)
        print(f'timeOverrides: {len(out)} dato(er) fra {p}')
        return out
    print('  ADVARSEL: timeOverrides kunne ikke laeses — bruger standardtider')
    return {}


def parse_weeks(spec, total_weeks):
    """'3' -> [3]; '3-17' -> [3..17]; 'all' -> [1..total]. Fejler på ugyldigt."""
    spec = (spec or '').strip().lower()
    if spec in ('all', 'alle', '*'):
        out = list(range(1, total_weeks + 1))
    elif '-' in spec:
        a, b = spec.split('-', 1)
        out = list(range(int(a), int(b) + 1))
    else:
        out = [int(spec)]
    assert out and all(1 <= w <= total_weeks for w in out), \
        f'Ugyldig uge(r): {spec!r} (programmet har {total_weeks} uger)'
    return out


def main():
    import requests
    import json as _json

    CLIENT_ID     = os.environ['AZURE_CLIENT_ID']
    TENANT_ID     = os.environ['AZURE_TENANT_ID']
    CLIENT_SECRET = os.environ['AZURE_CLIENT_SECRET']
    API_KEY       = os.environ['INTERVALS_API_KEY']
    ATHLETE_ID    = os.environ.get('INTERVALS_ATHLETE_ID') or 'i599466'  # fallback: secret har vist sig tom
    WEEK_IN       = os.environ.get('WEEK', '2').strip()
    USER          = 'kennet@hammerby.com'
    GRAPH         = f'https://graph.microsoft.com/v1.0/users/{USER}'
    TIMEOUT       = 30

    # Program og uge (rettet 3/9-2026): WEEK er ugenummer i programmet PROGRAM
    # (program-id fra plan.json -> programs). Mangler PROGRAM, bruges det program
    # der er aktivt i dag (modules/programs.py). Var før bundet til det ene legacy
    # 'program'-felt og frøs derfor på sidste uge ved programskifte.
    from modules import programs as _programs
    _plan = _json.load(open(os.path.join(_REPO_ROOT, 'data', 'plan.json'), encoding='utf-8'))
    PROGRAM_ID = os.environ.get('PROGRAM', '').strip()
    if PROGRAM_ID:
        _prog = _programs.list_programs(_plan).get(PROGRAM_ID)
        assert _prog, f'Ukendt program: {PROGRAM_ID!r}'
    else:
        _prog = _programs.active_program(_plan, 'kennet')
        PROGRAM_ID = _prog['id']
    PLAN_START_D = date.fromisoformat(_prog['start'])
    TOTAL_WEEKS  = _prog['totalWeeks']

    weeks = parse_weeks(WEEK_IN, TOTAL_WEEKS)
    print(f'Program {PROGRAM_ID}: uge {weeks[0]}' + (f'-{weeks[-1]}' if len(weeks) > 1 else '') + f' af {TOTAL_WEEKS}')

    # Token
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
    print('Token OK')

    def sync_week(WEEK):
        week_start = PLAN_START_D + timedelta(weeks=WEEK-1)
        week_end   = week_start + timedelta(days=6)
        print(f'Uge {WEEK}: {week_start} til {week_end}')

        # TRIN 1: Hent workouts fra Intervals FØRST.
        # Rækkefølgen er kritisk: sletter vi før vi ved at der er noget at oprette,
        # efterlader en Intervals-fejl kalenderen tom. Gælder især uovervåget cron-kørsel.
        r = requests.get(
            f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events',
            auth=('API_KEY', API_KEY),
            params={'oldest': f'{week_start}T00:00:00', 'newest': f'{week_end}T23:59:00',
                    'category': 'WORKOUT'},
            timeout=TIMEOUT
        )
        if r.status_code != 200:
            print(f'FEJL: Intervals GET returnerede {r.status_code}: {r.text[:200]}')
            raise SystemExit(1)
        workouts = r.json()
        print(f'{len(workouts)} workouts fra Intervals')
        if not workouts:
            if len(weeks) > 1:
                # Rækkesynk (11/9-2026): en tom uge (fx Japan) må ikke vælte resten —
                # og den ryddes heller ikke, for vi ved ikke om Intervals bare svigtede.
                print('ADVARSEL: 0 workouts fra Intervals — ugen springes over (ikke ryddet).')
                return 0, 0
            print('FEJL: 0 workouts fra Intervals — forventede en planlagt uge. Afbryder.')
            raise SystemExit(1)

        # TRIN 2: Slet eksisterende Traening-events — først nu, hvor workouts er i hus
        url    = f'{GRAPH}/calendarView'
        params = {'startDateTime': f'{week_start}T00:00:00',
                  'endDateTime':   f'{week_end}T23:59:59',
                  '$select': 'id,subject,categories', '$top': '50'}
        existing = []
        while url:
            r = requests.get(url, headers=hdrs_get, params=params, timeout=TIMEOUT)
            params = None
            body   = r.json()
            existing.extend(body.get('value', []))
            url = body.get('@odata.nextLink')

        deleted = 0
        for e in existing:
            if any(c in ('Træning', 'Traening') for c in e.get('categories', [])):
                dr = requests.delete(f'{GRAPH}/events/{e["id"]}', headers=hdrs, timeout=TIMEOUT)
                if dr.status_code in (204, 404):
                    print(f'  Slettet: {e["subject"]}')
                    deleted += 1
                else:
                    print(f'  FEJL slet {e["subject"]}: {dr.status_code}')
        print(f'Slettet: {deleted}')

        # TRIN 3: Opret nye events — tider pr. dag via schedule_day (aldrig overlap)
        by_day = {}
        for w in workouts:
            by_day.setdefault((w.get('start_date_local') or '')[:10], []).append(w)
        ok = err = 0
        for dt in sorted(by_day):
            for w, start_dt in schedule_day(by_day[dt], TIME_OVERRIDES.get(dt)):
                event = event_body(w, start_dt)
                resp = requests.post(f'{GRAPH}/events', headers=hdrs, json=event, timeout=TIMEOUT)
                if resp.status_code == 201:
                    print(f'  Oprettet: {dt} {event["subject"]} {start_dt:%H:%M}')
                    ok += 1
                else:
                    print(f'  FEJL opret {dt} {w.get("name", "Træning")}: {resp.status_code} {resp.text[:120]}')
                    err += 1
        return ok, err

    TIME_OVERRIDES = _load_time_overrides(_REPO_ROOT)
    tot_ok = tot_err = 0
    for WEEK in weeks:
        ok, err = sync_week(WEEK)
        tot_ok += ok
        tot_err += err
    print(f'Oprettet: {tot_ok} | Fejl: {tot_err}')
    if tot_err > 0:
        raise SystemExit(1)
    print('DONE')


if __name__ == '__main__':
    main()
