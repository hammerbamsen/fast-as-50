"""Sessions, aktiviteter og planlagte workouts fra Intervals.icu."""
import math as _math
import re
from datetime import date, timedelta
from .config import (PLAN as _PLAN, ACTIVE_PROGRAM, TOTAL_WEEKS, PLAN_START, BASE, AUTH, api_get, fix_enc, fmt, color_for, ctl_plan_for_week,
                      DAY_SHORT, BLOCK_TYPES, RUN_PACE_ZONES_SEC_PER_KM, BIKE_ZONES_WATTS, athlete_age)
from .af import monday_this_week
from . import programs as _programs


def current_week_no(today=None):
    """Ugenummer i det aktive program (clampet 1..TOTAL_WEEKS) — eneste sted
    ugen beregnes i dette modul. Ingen lokale (dato - start)//7-udtryk."""
    return _programs.week_no(ACTIVE_PROGRAM, today or date.today())

# ── Rep-for-rep-analyse af intervalpas ───────────────────────────────────────
# Et stykke tæller som "arbejde" hvis det er hurtigere/hårdere end target-zonens
# svage kant plus en tolerance. Tolerancen skal være stor nok til at fange en
# rep der blev løbet lidt for langsomt, men lille nok til at pauser aldrig
# ryger med (pauserne ligger typisk 50+ sek/km langsommere end target).
PACE_WORK_TOLERANCE_SEC  = 20    # sek/km under Z-bandets langsomme kant
BIKE_WORK_TOLERANCE_PCT  = 8     # % under zonens nedre watt-grænse
MIN_REP_PIECE_SECS       = 15    # kortere stykker er støj (GPS-udsving)
MIN_REP_SECS             = 60    # en merged rep skal have reel varighed
REP_DRIFT_MIN            = 4     # mindre drift end dette er ikke et signal
REP_FLAG_MARK            = {'ok': '✅', 'fast': '⚡for hårdt', 'slow': '⚠️for blødt'}
MIN_PLANNED_WORK_SECS    = 120   # kortere arbejdstrin (strides, 1-min) kan ikke pace-vurderes
MAX_REP_OVERRUN          = 1.6
# Hvis en detekteret rep er mere end 1,6x det planlagte arbejdstrin, er
# pauserne blevet merged ind i repsene og hele analysen er vrøvl -- så
# dropper vi den og lader sessionsvurderingen stå. Det er en efterkontrol
# på det faktiske symptom; en teoretisk afstand mellem target-båndene duer
# ikke som filter, fordi arbejde og pause godt kan grænse op til hinanden
# på papiret (hometrainer Z3: begge rammer 76% FTP) og alligevel separere
# rent i praksis (219-222W arbejde vs. 169-171W pause).


def _threshold_sec():
    """Løbetærskel i sek/km fra plan.json (samme kilde som zonerne)."""
    z = ((_PLAN or {}).get('athletes', {}).get('kennet', {}) or {}).get('zones') or {}
    return z.get('thresholdSec')


def _ftp_watts():
    z = ((_PLAN or {}).get('athletes', {}).get('kennet', {}) or {}).get('zones') or {}
    return z.get('ftpW')


def bike_zone_watts(zone):
    """(lo, hi) watt for en cykelzone. (None, None) hvis ukendt."""
    band = (BIKE_ZONES_WATTS or {}).get(zone)
    return (band[0], band[1]) if band else (None, None)


def get_activities_since(days=10):
    """Rå Intervals-aktiviteter for de seneste `days` dage (inkl. i dag).

    Bruges af T3-adaptation, som har brug for et længere vindue end
    'denne uge'. Returnerer en liste (evt. tom) — aldrig None, så
    kalderen kan skelne 'ingen aktiviteter' fra 'ikke forsøgt'.
    """
    newest = date.today()
    oldest = newest - timedelta(days=days)
    r = api_get(f'{BASE}/activities', auth=AUTH,
                params={'oldest': str(oldest), 'newest': str(newest)})
    if r is not None and r.status_code == 200:
        try:
            return r.json()
        except Exception:
            return []
    return []


def get_weekly_tss_actual(plan_start, total_weeks):
    """Faktisk TSS pr. planuge, hele planperioden — historisk backfill.

    data.json baerer kun sessions-detaljer for den aktive uge, saa de
    historiske faktiske TSS-tal fandtes ikke noget sted. Den her henter dem
    i EET kald til /activities og bucketer paa planuge.

    Returnerer {uge_nr(int): tss(int)} for uger med mindst een aktivitet.
    Tom dict hvis kaldet fejler — kalderen maa ikke overskrive eksisterende
    data med tomt resultat.
    """
    newest = date.today()
    oldest = plan_start
    r = api_get(f'{BASE}/activities', auth=AUTH,
                params={'oldest': str(oldest), 'newest': str(newest)})
    if r is None or r.status_code != 200:
        print(f"  Uge-TSS backfill: kald fejlede ({getattr(r, 'status_code', 'ingen svar')})")
        return {}
    try:
        acts = r.json()
    except Exception as e:
        print(f"  Uge-TSS backfill: kunne ikke parse svar ({e})")
        return {}

    out = {}
    for a in acts:
        raw = a.get('start_date_local') or a.get('start_date') or ''
        try:
            d = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        week = (d - plan_start).days // 7 + 1
        if not (1 <= week <= total_weeks):
            continue
        load = a.get('icu_training_load') or a.get('training_load') or 0
        out[week] = out.get(week, 0) + round(load)
    print(f"  Uge-TSS backfill: {len(acts)} aktiviteter -> {len(out)} uger")
    return out


def get_activities_week():
    """TSS, løbe-km og done-sessioner fra mandag denne uge.
    Primær kilde: /activities (importerede Garmin-aktiviteter).
    Fallback: /events med paired_activity_id — fanger workouts markeret done
    i Intervals selv om Garmin-sync er forsinket."""
    monday = monday_this_week()
    today  = date.today()
    r = api_get(f'{BASE}/activities', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(today)})
    if r.status_code == 200:
        data = r.json()

        # Supplement: hent events med paired_activity_id for at fange
        # workouts der er markeret done i Intervals men endnu ikke synkroniseret
        # som aktiviteter fra Garmin
        r_ev = api_get(f'{BASE}/events', auth=AUTH,
                            params={'oldest': str(monday), 'newest': str(today)})
        if r_ev.status_code == 200:
            existing_ids = {a.get('id') for a in data}
            for ev in r_ev.json():
                paired_id = ev.get('paired_activity_id') or ev.get('activity_id')
                if not paired_id or paired_id in existing_ids:
                    continue
                # Hent den pågældende aktivitet direkte
                r_act = api_get(f'{BASE}/activities/{paired_id}', auth=AUTH)
                if r_act.status_code == 200:
                    act = r_act.json()
                    if act.get('id') not in existing_ids:
                        data.append(act)
                        existing_ids.add(act.get('id'))
                        print(f"  Fallback aktivitet hentet: {act.get('name')} ({act.get('type')})")
        print(f"  Aktiviteter denne uge: {len(data)}")
        for _a in data:
            print(f"    {_a.get('start_date_local','')[:16]} | {_a.get('type')} | {_a.get('name')} | "
                  f"moving={_a.get('moving_time')}s | icu_training_load={_a.get('icu_training_load')} | "
                  f"training_load={_a.get('training_load')}")
        total_tss = sum(a.get('icu_training_load') or a.get('training_load') or 0 for a in data)
        run_km = sum(
            (a.get('distance') or 0) / 1000
            for a in data
            if a.get('type') in ['Run', 'TrailRun', 'VirtualRun', 'IndoorRun']
        )
        bike_km = sum(
            (a.get('distance') or 0) / 1000
            for a in data
            if a.get('type') in ['Ride', 'VirtualRide', 'MountainBike', 'Cyclocross', 'Gravel', 'GravelRide']
        )
        # Træningstimer per type (i minutter)
        def mins(a): return round((a.get('moving_time') or a.get('elapsed_time') or 0) / 60, 0)
        def disc_of(a):
            t = a.get('type', '')
            if t in ['Ride','VirtualRide'] and a.get('commute'): return 'commute'
            if t in ['Run','TrailRun','VirtualRun','IndoorRun']:             return 'run'
            if t in ['Ride','VirtualRide','MountainBike','Cyclocross','Gravel','GravelRide']:       return 'bike'
            if t in ['Swim']:                                    return 'swim'
            if t in ['OpenWaterSwim']:                           return 'openwater'
            if t in ['Walk']:                                    return 'walk'
            if t in ['Hike']:                                    return 'hike'
            if t in ['WeightTraining','Workout','Strength','Yoga']: return 'strength'
            return 'free'
        train_mins = {}
        for a in data:
            d = disc_of(a)
            train_mins[d] = round(train_mins.get(d, 0) + mins(a), 0)
        # Fjern nul-værdier
        train_mins = {k: v for k, v in train_mins.items() if v > 0}
        # Byg done-map: {dag_short: [disc, ...]}
        done_map = {}
        for a in data:
            act_date = a.get('start_date_local', '')[:10]
            if not act_date:
                continue
            try:
                d = date.fromisoformat(act_date)
                day_idx = d.weekday()  # 0=Man
                day_key = DAY_SHORT[day_idx]
            except:
                continue
            atype = a.get('type', '')
            if atype in ['Ride','VirtualRide'] and a.get('commute'):
                disc = 'commute'
            elif atype in ['Run','TrailRun','VirtualRun','IndoorRun']:
                disc = 'run'
            elif atype in ['Ride','VirtualRide','MountainBike','Cyclocross','Gravel','GravelRide']:
                disc = 'bike'
            elif atype in ['Swim']:
                disc = 'swim'
            elif atype in ['OpenWaterSwim']:
                disc = 'openwater'
            elif atype in ['Walk']:
                disc = 'walk'
            elif atype in ['Hike']:
                disc = 'hike'
            elif atype in ['WeightTraining','Workout','Strength','Yoga']:
                disc = 'strength'
            else:
                disc = 'free'
            _tss      = round(a.get('icu_training_load') or a.get('training_load') or 0)
            _dur_secs = a.get('moving_time') or a.get('elapsed_time') or 0
            _dur_mins = round(_dur_secs / 60)
            # Zone-data til compliance-vurdering
            _compliance   = a.get('compliance')
            _pace_zt      = a.get('pace_zone_times')    # løb
            _power_zt     = a.get('icu_zone_times')     # cykel (list of {id, secs})
            _hr_zt        = a.get('icu_hr_zone_times')  # alle
            _distance_m   = a.get('distance')  # None hvis ikke rapporteret -- IKKE 0-fyldt her
            done_map.setdefault(day_key, []).append((
                a.get('start_date_local',''), disc, a.get('name') or atype, _tss, _dur_mins,
                _compliance, _pace_zt, _power_zt, _hr_zt, a.get('id'), _distance_m
            ))

        # Sortér efter tidspunkt og behold disc-navne + aktivitetsnavne
        for k in done_map:
            sorted_acts = sorted(done_map[k], key=lambda x: x[0])
            done_map[k] = [(disc, name, tss, dur_mins, compliance, pace_zt, power_zt, hr_zt, act_id, distance_m)
                           for _, disc, name, tss, dur_mins, compliance, pace_zt, power_zt, hr_zt, act_id, distance_m in sorted_acts]

        swim_m = sum(
            (a.get('distance') or 0)
            for a in data
            if a.get('type') in ['Swim', 'OpenWaterSwim']
        )
        return {
            'tss_week': round(total_tss, 0),
            'run_km':   round(run_km, 1),
            'bike_km':  round(bike_km, 1),
            'swim_m':   round(swim_m, 0),
            'train_mins': train_mins,
            'done_map': done_map,
        }
    return None

def compute_run_pace_zone_secs(act_id):
    """Beregn sek. pr. Friel-zone (Z1-Z6, i den rækkefølge) for en løbeaktivitet
    ud fra rå pace-stream (velocity_smooth), IKKE Intervals.icu's egen
    pace_zone_times -- da ICU's generiske %-tabel ikke matcher Kennets
    Friel-grænser for Z3 og opefter (bug fundet + verificeret 2/7-26).
    Returnerer [] hvis stream ikke kan hentes (fx svøm eller manglende GPS)."""
    if not act_id:
        return []
    r = api_get(f'https://intervals.icu/api/v1/activity/{act_id}/streams',
                auth=AUTH, params={'types': 'time,velocity_smooth'})
    if not r or r.status_code != 200:
        return []
    try:
        streams = {s['type']: s.get('data', []) for s in r.json()}
    except Exception:
        return []
    vel = streams.get('velocity_smooth') or []
    if not vel:
        return []
    zone_order = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6']
    secs = [0, 0, 0, 0, 0, 0]
    for v in vel:
        if not v or v <= 0:
            continue
        pace = 1000.0 / v  # sek/km
        for i, z in enumerate(zone_order):
            lo, hi = RUN_PACE_ZONES_SEC_PER_KM[z]
            if lo <= pace <= hi:
                secs[i] += 1
                break
    return secs


def count_planned_reps(ev):
    """Antal planlagte arbejdsintervaller på et event.

    Primært fra workout_doc (reps på et gruppe-step), sekundært fra navnet
    ('4×5 min', '5x3 min'). Returnerer None hvis det ikke kan udledes — så
    undlader vi at påstå at reps mangler.
    """
    doc = (ev or {}).get('workout_doc') or {}
    total = 0
    for step in (doc.get('steps') or []):
        if isinstance(step, dict) and step.get('steps'):
            total += int(step.get('reps') or 1)
    if total:
        return total
    m = re.search(r'(\d+)\s*[x×]\s*\d', fix_enc((ev or {}).get('name', '') or ''))
    return int(m.group(1)) if m else None


def _band(step, key, disc):
    """(lo, hi) i sek/km eller watt for et workout_doc-trin."""
    t = (step or {}).get(key) or {}
    lo_p, hi_p = t.get('start'), t.get('end')
    if lo_p is None or hi_p is None:
        return None
    if disc == 'run':
        thr = _threshold_sec()
        if not thr:
            return None
        # %pace: højere procent = hurtigere
        return (_math.ceil(thr * 100 / hi_p), _math.ceil(thr * 100 / lo_p) - 1)
    ftp = _ftp_watts()
    if not ftp:
        return None
    return (int(round(ftp * lo_p / 100)), int(round(ftp * hi_p / 100)))


def interval_spec(ev, disc):
    """Beskriver et intervalpas ud fra workout_doc, eller None hvis passet
    ikke egner sig til rep-for-rep-analyse.

    Navnet må ALDRIG være kilden — hverken til target eller til om passet er
    et intervalpas. 'Løb VO2 4×5 min Z4-Z5' hedder sådan af historiske
    grunde, og 'Hometrainer 3×15 min Z3' er et intervalpas selvom zonen er Z3.

    Tre krav, som alle findes i rigtige pas i planen:
      1. Et gruppe-step med reps >= 2.
      2. Arbejdstrinnet varer mindst MIN_PLANNED_WORK_SECS. 20-sekunders
         strides kan ikke pace-vurderes meningsfuldt — GPS-støjen er større
         end signalet.
      3. Arbejde og pause skal være tydeligt adskilt. 'Løb Z2 40 min +
         6×1 min race-pace' har arbejde 5:00-5:38 og jog >5:39 — de grænser
         op til hinanden, så pauserne ville blive merged ind i repsene og
         gøre analysen til vrøvl. Sådanne pas får sessionsvurdering i stedet.

    Returnerer {'reps', 'work_secs', 'target', 'rest'} eller None.
    """
    doc = (ev or {}).get('workout_doc') or {}
    key = 'pace' if disc == 'run' else 'power'
    best = None
    for step in (doc.get('steps') or []):
        if not isinstance(step, dict) or not step.get('steps'):
            continue
        reps = int(step.get('reps') or 1)
        if reps < 2:
            continue
        children = [c for c in step['steps'] if isinstance(c, dict)]
        bands = [(c, _band(c, key, disc)) for c in children]
        bands = [(c, b) for c, b in bands if b]
        if not bands:
            continue
        # Arbejdstrinnet = den hårdeste intensitet i gruppen
        work_c, work_b = (min(bands, key=lambda x: x[1][0]) if disc == 'run'
                          else max(bands, key=lambda x: x[1][1]))
        rest = [b for c, b in bands if c is not work_c]
        rest_b = (max(rest, key=lambda b: b[0]) if disc == 'run'
                  else min(rest, key=lambda b: b[1])) if rest else None
        cand = {'reps': reps, 'work_secs': int(work_c.get('duration') or 0),
                'target': work_b, 'rest': rest_b}
        if best is None or cand['work_secs'] > best['work_secs']:
            best = cand
    if not best or best['work_secs'] < MIN_PLANNED_WORK_SECS:
        return None

    return best


def planned_target_from_event(ev, disc):
    """(lo, hi) target for arbejdsintervallerne. (None, None) hvis ukendt."""
    spec = interval_spec(ev, disc)
    return spec['target'] if spec else (None, None)


def has_rep_structure(ev, disc):
    """Er dette et intervalpas der kan vurderes rep-for-rep?"""
    return interval_spec(ev, disc) is not None


def _pace_str(secs_per_km):
    """252.4 -> '4:12'."""
    if not secs_per_km or secs_per_km <= 0:
        return '-'
    s = int(round(secs_per_km))
    return f"{s // 60}:{s % 60:02d}"


def get_interval_reps(act_id, planned_zone, disc, streams=None, intervals=None,
                      target=None, spec=None):
    """Rep-for-rep-analyse af et intervalpas.

    Hvorfor ikke bare Intervals' egen opdeling: `type` er 'WORK' på stort set
    ALT (også opvarmning, pauser og cool-down) og `label` er altid None —
    Intervals matcher ikke mod den planlagte struktur, den auto-detekterer
    pace-/watt-skift. Oveni splittes én rep typisk i to stykker når tempoet
    ændrer sig undervejs (verificeret 6/8-26: rep 1 lå som 254s@4:13 + 46s@4:09).

    Derfor: merge sammenhængende detekterede stykker der er hurtigere/hårdere
    end target-zonens nedre kant + tolerance, og vægt pace/watt/HR efter tid.

    Returnerer liste af dicts:
      {'n', 'secs', 'pace_sec' (løb), 'watts' (cykel), 'hr', 'in_zone_pct',
       'flag': 'ok'/'fast'/'slow'}
    Tom liste hvis der ikke kan udledes reps.
    """
    if not act_id:
        return []

    # target kommer primært fra eventets workout_doc (den faktiske planlagte
    # pace/watt) -- zone-navnet er kun fallback, se planned_target_from_event.
    lo, hi = target if target and target[0] is not None else (None, None)
    rest = (spec or {}).get('rest')
    if disc == 'run':
        if lo is None:
            band = RUN_PACE_ZONES_SEC_PER_KM.get(planned_zone)
            if not band:
                return []
            lo, hi = band[0], band[1]      # sek/km: lo = hurtigst, hi = langsomst
        # Skillelinjen lægges midt mellem arbejdets langsomme kant og pausens
        # hurtige kant, når pausen er kendt. En fast tolerance på +20 sek/km
        # kunne ellers sluge pauserne på pas hvor de to ligger tæt.
        work_cut = ((hi + rest[0]) / 2.0 if rest and rest[0] > hi
                    else hi + PACE_WORK_TOLERANCE_SEC)
    elif disc == 'bike':
        if lo is None:
            lo, hi = bike_zone_watts(planned_zone)
        if lo is None:
            return []
        work_cut = ((lo + rest[1]) / 2.0 if rest and rest[1] < lo
                    else lo - (lo * BIKE_WORK_TOLERANCE_PCT / 100.0))
    else:
        return []

    if intervals is None:
        r = api_get(f'https://intervals.icu/api/v1/activity/{act_id}/intervals', auth=AUTH)
        if not r or r.status_code != 200:
            return []
        try:
            intervals = (r.json() or {}).get('icu_intervals') or []
        except Exception:
            return []
    if not intervals:
        return []

    def _effort(iv):
        """Intensitetsmål for et stykke: sek/km for løb, watt for cykel."""
        if disc == 'run':
            sp = iv.get('average_speed')
            return (1000.0 / sp) if sp and sp > 0 else None
        return iv.get('average_watts')

    def _is_work(iv):
        e = _effort(iv)
        if e is None or (iv.get('moving_time') or 0) < MIN_REP_PIECE_SECS:
            return False
        return e < work_cut if disc == 'run' else e > work_cut

    # Merge sammenhængende arbejdsstykker til reps
    groups, cur = [], []
    for iv in intervals:
        if _is_work(iv):
            cur.append(iv)
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    min_rep = MIN_REP_SECS
    if spec and spec.get('work_secs'):
        # En rep skal fylde mindst halvdelen af det planlagte arbejdstrin,
        # ellers er det et fragment -- ikke en gennemført rep.
        min_rep = max(MIN_REP_SECS, spec['work_secs'] * 0.5)
    groups = [g for g in groups if sum(x.get('moving_time') or 0 for x in g) >= min_rep]
    if not groups:
        return []
    planned_work = (spec or {}).get('work_secs') or 0
    if planned_work:
        longest = max(sum(x.get('moving_time') or 0 for x in g) for g in groups)
        if longest > planned_work * MAX_REP_OVERRUN:
            return []      # pauserne er merged ind -- analysen kan ikke bruges

    # Rå stream til in-zone-% pr. rep (samme kilde som Friel-zoneberegningen)
    if streams is None:
        types = 'time,velocity_smooth' if disc == 'run' else 'time,watts'
        rs = api_get(f'https://intervals.icu/api/v1/activity/{act_id}/streams',
                     auth=AUTH, params={'types': types})
        streams = {}
        if rs and rs.status_code == 200:
            try:
                streams = {s['type']: s.get('data', []) for s in rs.json()}
            except Exception:
                streams = {}
    series = (streams or {}).get('velocity_smooth' if disc == 'run' else 'watts') or []

    reps = []
    for n, grp in enumerate(groups, 1):
        secs = sum(x.get('moving_time') or 0 for x in grp)
        if not secs:
            continue
        eff = sum((_effort(x) or 0) * (x.get('moving_time') or 0) for x in grp) / secs
        hrs = [x for x in grp if x.get('average_heartrate')]
        hr = (round(sum(x['average_heartrate'] * (x.get('moving_time') or 0) for x in hrs)
                    / sum(x.get('moving_time') or 0 for x in hrs)) if hrs else None)

        in_zone_pct = None
        s_i, e_i = grp[0].get('start_index'), grp[-1].get('end_index')
        if series and s_i is not None and e_i is not None and e_i >= s_i:
            win = series[s_i:e_i + 1]
            vals = []
            for v in win:
                if v is None or v <= 0:
                    continue
                vals.append(1000.0 / v if disc == 'run' else v)
            if vals:
                in_zone_pct = round(sum(1 for v in vals if lo <= v <= hi) / len(vals) * 100, 1)

        if disc == 'run':
            flag = 'ok' if lo <= eff <= hi else ('fast' if eff < lo else 'slow')
        else:
            flag = 'ok' if lo <= eff <= hi else ('fast' if eff > hi else 'slow')

        rep = {'n': n, 'secs': int(secs), 'hr': hr,
               'in_zone_pct': in_zone_pct, 'flag': flag}
        if disc == 'run':
            rep['pace_sec'] = round(eff, 1)
        else:
            rep['watts'] = round(eff)
        reps.append(rep)
    return reps


def _half_drift(vals):
    """Drift = snit af sidste halvdel minus snit af første halvdel.

    Rep 1 vs. sidste rep alene er misvisende når tempoet veksler: 4:13 · 4:20 ·
    4:12 · 4:19 er ikke et drop-off på 6 sek/km, det er overpacing hver anden
    rep. Halvdel-mod-halvdel fanger reel udtrætning i stedet.
    """
    n = len(vals) // 2
    if n < 1:
        return 0
    first = sum(vals[:n]) / n
    last = sum(vals[-n:]) / n
    return round(last - first)


def summarize_reps(reps, planned_zone, disc, planned_reps=None, target=None):
    """Én linje der beskriver rep-for-rep-udførelsen — det coachen skal dømme på.

    Sessionsgennemsnit skjuler præcis det der betyder noget på et intervalpas:
    om rep 1 blev løbet for hurtigt og rep 4 faldt fra.
    """
    if not reps:
        return None
    if disc == 'run':
        band = target if target and target[0] is not None else (
            RUN_PACE_ZONES_SEC_PER_KM.get(planned_zone) or (0, 0))
        target_txt = f"target {_pace_str(band[0])}–{_pace_str(band[1])}/km"
        vals = [r['pace_sec'] for r in reps]
        parts = [f"{_pace_str(r['pace_sec'])} {REP_FLAG_MARK[r['flag']]}" for r in reps]
        unit = 'sek/km'
        drift = _half_drift(vals)              # positiv = langsommere til sidst
    else:
        lo, hi = target if target and target[0] is not None else bike_zone_watts(planned_zone)
        target_txt = f"target {lo}–{hi}W"
        vals = [r['watts'] for r in reps]
        parts = [f"{r['watts']}W {REP_FLAG_MARK[r['flag']]}" for r in reps]
        unit = 'W'
        drift = -_half_drift(vals)             # positiv = svagere til sidst

    line = f"{len(reps)} reps ({target_txt}): " + " · ".join(parts)
    if planned_reps and planned_reps != len(reps):
        line += f" — BEMÆRK: {planned_reps} reps var planlagt, {len(reps)} udført"

    n_fast = sum(1 for r in reps if r['flag'] == 'fast')
    n_slow = sum(1 for r in reps if r['flag'] == 'slow')
    if n_fast:
        line += (f" — {n_fast} af {len(reps)} reps var HÅRDERE end target "
                 f"(overpacing, ikke en sejr)")
    if n_slow:
        line += f" — {n_slow} af {len(reps)} reps nåede ikke op på target"
    if len(reps) >= 2 and abs(drift) >= REP_DRIFT_MIN:
        retning = 'drop-off' if drift > 0 else 'negative split'
        line += f" — {retning} {abs(drift)} {unit} (sidste halvdel mod første)"
    if not n_fast and not n_slow and abs(drift) < REP_DRIFT_MIN:
        line += " — jævnt udført, alle reps i zone"
    return line


def get_workout_compliance_this_week(events_this_week, activities_this_week):
    """Beregner zone-compliance for hvert planlagt workout denne uge.

    Matcher planlagte events med faktiske aktiviteter via paired_activity_id,
    og ekstraherer zone-fordeling (pace/power/HR) pr. disciplin.

    Returnerer liste af dicts:
      {
        'day':         str,    # 'Tir'
        'date':        str,    # '2026-06-23'
        'label':       str,    # 'Løb Z2 45 min'
        'disc':        str,    # 'run'
        'planned_zone': str,   # 'Z2'
        'intervals_compliance': float,  # 104.3 (Intervals' egen score, 0 = ikke paired)
        'zone_pct':    float,  # 14.7 (% tid i target zone)
        'hr_z1_pct':   float,  # 97.9 (% tid i HR-Z1, nyttigt for drift-vurdering)
        'hr_z2plus_pct': float, # 2.1 (% tid i HR-Z2+, viser faktisk HR-intensitet)
        'zone_flag':   str,    # 'ok' / 'under' / 'over' / 'no_data'
        'metric':      str,    # 'pace' / 'power' / 'hr'
        'moving_mins': float,  # 47
        'planned_mins': float, # 45
        'note':        str,    # Coach-fortolkning
      }
    """
    TYPE_MAP = {
        'Run': 'run', 'TrailRun': 'run', 'VirtualRun': 'run', 'IndoorRun': 'run',
        'Ride': 'bike', 'VirtualRide': 'bike', 'MountainBike': 'bike',
        'Cyclocross': 'bike', 'Gravel': 'bike', 'GravelRide': 'bike',
        'Swim': 'swim', 'OpenWaterSwim': 'swim',
        'WeightTraining': 'strength', 'Workout': 'strength', 'Strength': 'strength',
    }
    DAY_SHORT_LOCAL = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"]

    # Byg lookup: activity_id -> aktivitet
    act_by_id = {a.get('id'): a for a in (activities_this_week or [])}
    # Byg lookup: (dato, disc) -> aktivitet (fallback)
    # Pendlingsture holdes UDE: de er ikke dagens planlagte pas. Uden det her
    # bliver en 12-min pendlertur limet på et 80-min hometrainer-pas og vist
    # som "15% gennemfoert" — passet ser brugt ud foer det er koert.
    # (Beskyttelsen i paired-grenen nedenfor rammer ikke her, fordi Intervals
    #  ikke har sat paired_event_id paa en fritstaaende pendlertur.)
    act_by_date_disc = {}
    for a in (activities_this_week or []):
        if a.get('commute') or (a.get('sub_type') or '').upper() == 'COMMUTE':
            continue
        dt = a.get('start_date_local', '')[:10]
        disc = TYPE_MAP.get(a.get('type', ''), 'free')
        key = (dt, disc)
        if key not in act_by_date_disc:
            act_by_date_disc[key] = a

    def detect_planned_zone(event_name):
        """Udtræk planlagt zone fra workout-navn."""
        name_upper = (event_name or '').upper()
        for z in ['Z5', 'Z4', 'Z3', 'Z2', 'Z1']:
            if z in name_upper:
                return z
        if any(kw in name_upper for kw in ['INTERVAL', 'BJERG', 'VO2', 'TEMPO']):
            return 'Z4'
        if any(kw in name_upper for kw in ['RECOVERY', 'LET', 'EASY']):
            return 'Z1'
        return 'Z2'  # default

    def zone_target_floor(planned_zone, disc):
        """Mindste acceptable % tid i target zone (Friel-baseret)."""
        if planned_zone in ('Z4', 'Z5'):
            return 15   # Interval-træning: lav pct er OK (restitutionstid ml. intervals)
        if disc == 'swim':
            return 30   # Svøm: zone-måling er HR, mere spredt
        if disc == 'bike':
            return 40   # Cykel: Z2+Z3 samlet, coasting+trapper giver naturligt mere Z1
        return 55       # Løb Z2: pace er præcis nok til strikt krav

    results = []
    for ev in (events_this_week or []):
        if ev.get('category') not in ('WORKOUT', None):
            continue
        ev_type = ev.get('type', '')
        disc = TYPE_MAP.get(ev_type, 'free')
        if disc in ('free', 'strength'):
            continue  # Ingen zone-vurdering for styrke/gåtur

        ev_date = ev.get('start_date_local', '')[:10]
        ev_name = fix_enc(ev.get('name', ''))
        planned_zone = detect_planned_zone(ev_name)
        planned_secs = ev.get('moving_time') or ev.get('elapsed_time') or 0
        planned_mins = round(planned_secs / 60) if planned_secs else None

        try:
            dt = date.fromisoformat(ev_date)
            day_key = DAY_SHORT_LOCAL[dt.weekday()]
        except Exception:
            day_key = '?'

        # Find matchet aktivitet
        act = None
        paired_id = ev.get('paired_activity_id') or ev.get('activity_id')
        if paired_id and paired_id in act_by_id:
            candidate = act_by_id[paired_id]
            if candidate.get('commute') or (candidate.get('sub_type') or '').upper() == 'COMMUTE':
                # Paired aktivitet er en pendlingstur — find ikke-commute alternativ samme dag+type
                non_commute = [
                    a for a in (activities_this_week or [])
                    if a.get('start_date_local', '')[:10] == ev_date
                    and TYPE_MAP.get(a.get('type', ''), 'free') == disc
                    and not a.get('commute')
                    and (a.get('sub_type') or '').upper() != 'COMMUTE'
                ]
                if non_commute:
                    # Vælg den tidsmæssigt tætteste på eventet
                    act = non_commute[0]
                    print(f"  ⚠️ Paired aktivitet for '{ev_name}' er commute — bruger ikke-commute alternativ: '{act.get('name')}'")
                else:
                    act = candidate  # ingen alternativ fundet, brug commute som fallback
                    print(f"  ⚠️ Paired aktivitet for '{ev_name}' er commute — ingen alternativ fundet")
            else:
                act = candidate
        else:
            act = act_by_date_disc.get((ev_date, disc))

        if not act:
            results.append({
                'day': day_key, 'date': ev_date, 'label': ev_name,
                'disc': disc, 'planned_zone': planned_zone,
                'intervals_compliance': None, 'zone_pct': None,
                'hr_z1_pct': None, 'hr_z2plus_pct': None,
                'zone_flag': 'no_data', 'metric': None,
                'moving_mins': None, 'planned_mins': planned_mins,
                'distance_m': None,
                'planned_distance_m': parse_planned_distance_m(ev_name),
                'note': 'Ingen matchet aktivitet fundet',
            })
            continue

        moving_time = act.get('moving_time') or act.get('elapsed_time') or 0
        moving_mins = round(moving_time / 60, 0) if moving_time else 0
        # Faktisk distance (tilføjet 8/8-2026): uden den så coach-prompten kun
        # planens label og citerede plantallet som gennemført distance.
        distance_m = act.get('distance')
        intervals_compliance = act.get('compliance')
        if intervals_compliance == 0.0:
            intervals_compliance = None  # 0.0 = ikke paired, None = ukendt

        # HR-zone data (fælles for alle discipliner)
        hr_zt = act.get('icu_hr_zone_times') or []
        total_hr = sum(hr_zt) if hr_zt else 0
        hr_z1_pct = round(hr_zt[0] / total_hr * 100, 1) if total_hr and hr_zt else None
        hr_z2plus_pct = round(sum(hr_zt[1:]) / total_hr * 100, 1) if total_hr and len(hr_zt) > 1 else None

        # Zone-kilde og beregning per disciplin
        zone_pct = None
        metric = None

        if disc == 'run':
            # Primær: rå pace-stream bucketet mod Kennets egne Friel-zoner.
            # (IKKE act['pace_zone_times'] -- ICU's generiske 7-zone %-tabel
            # matcher ikke Friel-grænserne for Z3+, se compute_run_pace_zone_secs.)
            pzt = compute_run_pace_zone_secs(act.get('id'))
            if pzt and sum(pzt) > 0:
                total_p = sum(pzt)
                if planned_zone in ('Z4', 'Z5'):
                    # Interval-zone: Z4+Z5 tælles samlet (naturlig rep-til-rep
                    # variation omkring threshold-pace er ikke "for langsomt/hurtigt")
                    zone_pct = round((pzt[3] + pzt[4]) / total_p * 100, 1)
                else:
                    z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
                    zone_pct = round(pzt[z_idx] / total_p * 100, 1) if z_idx < len(pzt) else 0
                metric = 'pace'
            elif hr_zt and total_hr > 0:
                z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
                if planned_zone in ('Z4', 'Z5') and z_idx + 1 < len(hr_zt):
                    zone_pct = round((hr_zt[z_idx] + hr_zt[z_idx + 1]) / total_hr * 100, 1)
                else:
                    zone_pct = round(hr_zt[z_idx] / total_hr * 100, 1) if z_idx < len(hr_zt) else 0
                metric = 'hr'

        elif disc == 'bike':
            # Primær: icu_zone_times (power)
            # Trim warmup+cooldown+coasting fra Z1 så opvarmning og nedkørsler
            # (0W frihjul, typisk på kuperede/gravel-ruter) ikke forvrænger zone-billedet
            coasting_secs = act.get('coasting_time') or 0
            moving_total = act.get('moving_time') or act.get('elapsed_time') or 0
            high_coasting = bool(moving_total and coasting_secs / moving_total > 0.10)
            pzt_raw = act.get('icu_zone_times') or []
            if pzt_raw:
                pzt = [z.get('secs', 0) for z in pzt_raw if isinstance(z, dict)]
                # Træk warmup+cooldown+coasting fra Z1 (de sidder næsten altid i Z1)
                trim_secs = (act.get('icu_warmup_time') or 0) + (act.get('icu_cooldown_time') or 0) + coasting_secs
                if trim_secs > 0 and pzt:
                    pzt[0] = max(0, pzt[0] - trim_secs)
                total_p = sum(pzt)
                if total_p > 0:
                    if planned_zone == 'Z2':
                        # Z2+Z3 tælles samlet (Friel: Z3 er acceptabel overskridelse i aerob base)
                        z2_secs = pzt[1] if len(pzt) > 1 else 0
                        z3_secs = pzt[2] if len(pzt) > 2 else 0
                        zone_pct = round((z2_secs + z3_secs) / total_p * 100, 1)
                        metric = 'power (Z2+Z3)'
                    else:
                        z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
                        zone_pct = round(pzt[z_idx] / total_p * 100, 1) if z_idx < len(pzt) else 0
                        metric = 'power'
            if zone_pct is None and hr_zt and total_hr > 0:
                z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
                zone_pct = round(hr_zt[z_idx] / total_hr * 100, 1) if z_idx < len(hr_zt) else 0
                metric = 'hr'

        elif disc == 'swim':
            # Kun HR tilgængeligt for svøm
            if hr_zt and total_hr > 0:
                z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
                zone_pct = round(hr_zt[z_idx] / total_hr * 100, 1) if z_idx < len(hr_zt) else 0
                metric = 'hr'

        # Zone-flag
        if zone_pct is None:
            zone_flag = 'no_data'
        else:
            floor = zone_target_floor(planned_zone, disc)
            zone_flag = 'ok' if zone_pct >= floor else 'under'

        # Bestem altid (uanset ok/under) hvor evt. afvigende tid faktisk landede
        # ift. target-zonen — hurtigere/højere zone vs. langsommere/lavere zone.
        # Gæt ALDRIG retning ud fra HR alene: lav HR ved en for hurtig pace/watt
        # betyder ikke lav intensitet, bare at HR ikke nåede at følge med.
        # Z4/Z5 (interval-træning) undtages: recovery mellem intervals giver
        # naturligt meget tid i lavere zoner — det er IKKE "for roligt".
        direction = None
        below_pct = above_pct = None
        is_interval_zone = planned_zone in ('Z4', 'Z5')
        if not is_interval_zone and disc == 'run' and metric == 'pace' and pzt and sum(pzt) > 0:
            total_p = sum(pzt)
            z_idx = int(planned_zone[1]) - 1 if planned_zone.startswith('Z') else 1
            below_pct = round(sum(pzt[:z_idx]) / total_p * 100, 1) if z_idx > 0 else 0.0
            above_pct = round(sum(pzt[z_idx + 1:]) / total_p * 100, 1)
            if above_pct - below_pct >= 10:
                direction = 'fast'
            elif below_pct - above_pct >= 10:
                direction = 'slow'
        elif not is_interval_zone and disc == 'bike' and metric and metric.startswith('power') and pzt and sum(pzt) > 0:
            total_p = sum(pzt)
            target_idxs = {1, 2} if planned_zone == 'Z2' else {int(planned_zone[1]) - 1}
            below_pct = round(sum(v for i, v in enumerate(pzt) if i < min(target_idxs)) / total_p * 100, 1)
            above_pct = round(sum(v for i, v in enumerate(pzt) if i > max(target_idxs)) / total_p * 100, 1)
            if above_pct - below_pct >= 10:
                direction = 'fast'
            elif below_pct - above_pct >= 10:
                direction = 'slow'

        # Coaching-note
        note = ''
        if zone_flag == 'no_data':
            note = 'Ingen zone-data'
        elif disc == 'run' and metric == 'pace':
            combined_note = ' (Z4+Z5 kombineret)' if planned_zone in ('Z4', 'Z5') else ''
            base = f'{zone_pct}% i {planned_zone} (pace-zone){combined_note}'
            tag = ' — on target' if zone_flag == 'ok' else f' — under {floor}%-målet'
            if direction == 'fast':
                note = (f'{base}{tag}, men {above_pct}% af tiden lå i en HURTIGERE pace-zone end target '
                        f'(HR-Z1 = {hr_z1_pct}% — HR nåede ikke at følge med en for høj pace). Sænk tempoet.')
            elif direction == 'slow':
                note = (f'{base}{tag}, og {below_pct}% lå i en LANGSOMMERE pace-zone — '
                        f'løbet for roligt, overvej at skrue op for tempoet')
            else:
                note = f'{base}{tag}'
        elif disc == 'bike':
            base = f'{zone_pct}% i {planned_zone} ({metric})'
            tag = ' — on target' if zone_flag == 'ok' else f' — under {floor}%-målet (Z2+Z3 kombineret)'
            np_watts = act.get('icu_weighted_avg_watts')
            coasting_note = ''
            if high_coasting and moving_total:
                coasting_pct = round(coasting_secs / moving_total * 100, 1)
                coasting_note = (f' (NB: {coasting_pct}% coasting/frihjul — sandsynligt kuperet/gravel-terræn; '
                                  f'NP={np_watts}W er et mere retvisende effekt-mål end rå tid-i-zone her)')
            if direction == 'fast':
                if zone_flag == 'ok':
                    note = (f'{base}{tag}, {above_pct}% af tiden lå i højere watt-zone end target '
                             f'(fint hvis det var bevidste stigninger/indsatser){coasting_note}')
                else:
                    note = (f'{base}{tag}, men {above_pct}% af tiden lå i en HØJERE watt-zone end target — '
                            f'kørt for hårdt. Sænk wattene.{coasting_note}')
            elif direction == 'slow':
                if zone_flag == 'ok':
                    # Zonen er allerede opfyldt (>= floor) — "slow"-signalet er kun kontekst,
                    # ALDRIG en instruktion om at "skrue op", da det modsiger on-target-vurderingen
                    note = (f'{base}{tag}, {below_pct}% af tiden lå i lavere watt-zone '
                             f'(typisk nedkørsler/frihjul på kuperet terræn, ikke lav indsats){coasting_note}')
                else:
                    note = f'{base}{tag}, og {below_pct}% lå i en LAVERE watt-zone — skru wattene op{coasting_note}'
            else:
                note = f'{base}{tag}{coasting_note}'
        elif zone_flag == 'ok':
            note = f'{zone_pct}% i {planned_zone} ({metric}) — on target'
        else:
            note = f'{zone_pct}% i {planned_zone} ({metric}) — under {floor}%-målet'

        # Tilføj Intervals compliance hvis tilgængeligt
        if intervals_compliance and intervals_compliance > 0:
            note = f'Steps: {intervals_compliance:.0f}% · {note}'

        # ── Rep-for-rep på intervalpas ──────────────────────────────────────
        # Sessionsgennemsnittet er ubrugeligt her: på 4×5 min med 15 min
        # opvarmning, 9 min pauser og 10 min cool-down er 30% tid-i-zone det
        # matematiske maksimum, og floor'en stod på 15%. Et pas hvor rep 1 og 3
        # blev løbet i Z5 og rep 4 faldt fra, scorede "on target".
        reps = []
        if disc in ('run', 'bike') and has_rep_structure(ev, disc):
            spec = interval_spec(ev, disc)
            tgt = spec['target']
            reps = get_interval_reps(act.get('id'), planned_zone, disc,
                                     target=tgt, spec=spec)
            rep_line = summarize_reps(reps, planned_zone, disc,
                                      planned_reps=spec['reps'], target=tgt)
            if rep_line:
                note = f'{rep_line} · [sessionssnit: {note}]'
                # Flag'et skal afspejle rep-udførelsen, ikke tid-i-zone
                zone_flag = 'ok' if all(r['flag'] == 'ok' for r in reps) else 'under'

        results.append({
            'day': day_key, 'date': ev_date, 'label': ev_name,
            'disc': disc, 'planned_zone': planned_zone,
            'intervals_compliance': intervals_compliance,
            'zone_pct': zone_pct, 'hr_z1_pct': hr_z1_pct,
            'hr_z2plus_pct': hr_z2plus_pct,
            'zone_flag': zone_flag, 'metric': metric,
            'moving_mins': moving_mins, 'planned_mins': planned_mins,
            'distance_m': distance_m,
            'planned_distance_m': parse_planned_distance_m(ev_name),
            'reps': reps,
            'note': note,
        })

        print(f"  Zone-compliance {day_key} {ev_name[:30]}: {note}")

    return results


def format_compliance_for_prompt(compliance_list):
    """Formaterer compliance-liste til en kompakt streng til AI-prompten."""
    if not compliance_list:
        return None
    lines = []
    for c in compliance_list:
        day = c.get('day', '?')
        label = c.get('label', '')[:30]
        flag = c.get('zone_flag', 'no_data')
        note = c.get('note', '')
        moving = c.get('moving_mins')
        planned = c.get('planned_mins')

        # FAKTISKE TAL (8/8-2026): label'en er PLANEN. Uden faktisk distance her
        # citerede modellen plantallet fra label'en som gennemført distance —
        # 28,2 km løbet blev refereret som "29 km" fordi 29 stod i planens navn.
        # Distance vises derfor altid når den findes, med plantallet efter skråstreg.
        dist_m = c.get('distance_m')
        planned_dist_m = c.get('planned_distance_m')
        parts = []
        if dist_m:
            # Svøm i meter, løb/cykel i km — '1,4 km' skjuler den præcision der
            # afgør om en 2500 m generalprøve blev gennemført.
            if c.get('disc') in ('swim', 'openwater'):
                parts.append(f'{int(round(dist_m))}' +
                             (f'/{int(round(planned_dist_m))}' if planned_dist_m else '') + ' m')
            else:
                _km = lambda v: f'{v / 1000:.1f}'.replace('.', ',')
                parts.append(_km(dist_m) +
                             (f'/{_km(planned_dist_m)}' if planned_dist_m else '') + ' km')
        if moving and planned:
            parts.append(f'{int(moving)}/{int(planned)} min')
        elif moving:
            parts.append(f'{int(moving)} min')
        dur_str = f' ({" · ".join(parts)})' if parts else ''

        if flag == 'no_data':
            lines.append(f'- {day}: {label}{dur_str} → ikke gennemført')
        elif flag == 'ok':
            lines.append(f'- {day}: {label}{dur_str} → ✅ {note}')
        else:
            lines.append(f'- {day}: {label}{dur_str} → ⚠️  {note}')

        # Rep-detaljer som egen linje, så de ikke drukner i sessionsnoten
        reps = c.get('reps') or []
        if reps:
            det = []
            for r in reps:
                v = (_pace_str(r['pace_sec']) + '/km') if 'pace_sec' in r else f"{r.get('watts')}W"
                hr = f", {r['hr']} bpm" if r.get('hr') else ''
                inz = f", {r['in_zone_pct']}% i zone" if r.get('in_zone_pct') is not None else ''
                det.append(f"    rep {r['n']}: {r['secs'] // 60}:{r['secs'] % 60:02d} · {v}{hr}{inz}"
                           f" · {REP_FLAG_MARK[r['flag']]}")
            lines.extend(det)
    return '\n'.join(lines)


def get_planned_mins_this_week():
    """Henter planlagt træningstid i minutter fra Intervals denne uge.
    Bruger moving_time (sek), ellers estimated_moving_time, ellers 0.
    """
    today  = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    r = api_get(f'{BASE}/events', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(sunday)})
    if r.status_code != 200:
        print(f"  Planned mins API fejl: {r.status_code}")
        return 0
    events = r.json()
    print(f"  Events denne uge: {len(events)}")
    # Et enkelt pas > 6t er ikke reelt — det er korrupt event-data (fx en
    # svømning med moving_time = 132240s ≈ 36t). Sådanne events afvises, så
    # de ikke oppuster ugens planlagte tid (var årsag til "48t 48m"-fejlen).
    MAX_SESSION_SECS = 6 * 3600
    total_mins = 0
    for e in events:
        if e.get('category') != 'WORKOUT':
            continue
        # Varighed i sekunder — moving_time bærer den planlagte varighed på events.
        # Intervals leverer disse felter i sekunder; ingen gætte-heuristik på enhed.
        secs = (e.get('moving_time') or
                e.get('elapsed_time') or
                e.get('indoor_time') or
                e.get('planned_duration') or 0)
        if not secs or secs <= 0:
            print(f"    Springer over (ingen varighed): {e.get('name','')}")
            continue
        if secs > MAX_SESSION_SECS:
            print(f"    ⚠️ Urealistisk varighed {secs}s ({secs/3600:.1f}t) — data-fejl, springes over: {e.get('name','')}")
            continue
        mins = secs / 60
        total_mins += mins
        print(f"    Event: {e.get('name','')} secs={secs} mins={mins:.0f}")
    result = round(total_mins, 0)
    print(f"  Planlagt total: {result} min")
    return result

def planned_tss_this_week():
    """Estimerer planlagt TSS live fra Intervals events denne uge.
    Intervals giver ikke altid 'load' på planlagte workouts, så vi estimerer
    fra varighed (moving_time) + zone via IF-model: TSS/time = IF^2 * 100.
    Falder tilbage til hardcodet tabel hvis API fejler eller ingen events.
    """
    today  = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    # Fallback (bruges kun hvis live-data ikke kan hentes): ugens tssTarget
    # fra det aktive program i plan.json — ikke en hardkodet uge-tabel.
    week_num = current_week_no(today)
    fallback = _programs.week_meta(ACTIVE_PROGRAM, week_num).get('tssTarget') or 400

    r = api_get(f'{BASE}/events', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(sunday)})
    if r.status_code != 200:
        print(f"  Planned TSS API fejl: {r.status_code} — bruger fallback {fallback}")
        return fallback

    events = r.json()
    IF = {'Z1':0.55,'Z2':0.70,'Z3':0.80,'Z4':0.90,'Z5':1.0}
    total_tss = 0
    used_live = False

    for e in events:
        if e.get('category') not in ('WORKOUT', None):
            continue
        name = (e.get('name') or '')
        # 1) Hvis Intervals selv har en load/TSS, brug den
        load = e.get('load') or e.get('icu_training_load')
        if load:
            total_tss += load
            used_live = True
            continue
        # 2) Ellers estimer fra varighed + zone
        secs = (e.get('moving_time') or e.get('elapsed_time') or
                e.get('indoor_time') or e.get('planned_duration') or 0)
        if not secs:
            continue
        if secs > 6 * 3600:   # korrupt varighed (samme guard som planlagt tid) — udelad af TSS-estimat
            print(f"    ⚠️ Urealistisk varighed på '{name}' ({secs/3600:.1f}t) — udelades af TSS-estimat")
            continue
        hrs = secs / 3600
        nl = name.lower()
        # Bestem zone fra navnet
        zone = 'Z2'
        for z in ['Z5','Z4','Z3','Z2','Z1']:
            if z.lower() in nl:
                zone = z; break
        if 'interval' in nl or 'bjerg' in nl:
            zone = 'Z4'
        # Disciplinspecifik justering
        if 'styrke' in nl or e.get('type') in ('WeightTraining','Workout'):
            tss = hrs * 40            # styrke ~40 TSS/time
        elif 'svøm' in nl or e.get('type') == 'Swim':
            tss = hrs * 55            # svøm lidt højere intensitet
        else:
            tss = hrs * (IF[zone]**2 * 100)
        total_tss += tss
        used_live = True

    result = round(total_tss)
    if result == 0:
        print(f"  Ingen brugbare events med TSS/varighed — bruger fallback {fallback}")
        return fallback
    print(f"  Planlagt TSS (live estimat): {result}")
    return result

def parse_planned_mins(label):
    """Parser planlagt varighed fra label. Fx 'Lang løb Z2 90 min' → 90."""
    m = re.search(r'(\d+)\s*min', label or '', re.IGNORECASE)
    return int(m.group(1)) if m else None

def parse_planned_distance_m(label):
    """Parser planlagt distance i meter fra label.

    Meter: 'Svøm 2500m SAMMENHÆNGENDE' -> 2500. Kun 3-5-cifrede tal, så
    årstal/sekunder/'min' ikke giver falske match.
    Km (tilføjet 8/8-2026): 'Lang løb Z2 29 km' -> 29000, 'Løb 28-30 km' -> 30000,
    'Løb ... 21,3 km' -> 21300. Uden km-grenen havde løbe- og cykelpas ALDRIG et
    distance-mål, og coach-prompten citerede derfor planens km-tal som om det var
    den faktisk løbne distance (28,2 km blev til "29 km").
    Range-labels bruger den ØVRE grænse som mål — både for meter og km.
    """
    text = label or ''
    km = re.search(r'(\d{1,3}(?:[.,]\d+)?)(?:\s*[-–]\s*(\d{1,3}(?:[.,]\d+)?))?\s*km\b',
                   text, re.IGNORECASE)
    if km:
        val = (km.group(2) or km.group(1)).replace(',', '.')
        return int(round(float(val) * 1000))
    m = re.search(r'(\d{3,5})(?:[-–](\d{3,5}))?\s*m\b', text)
    if not m:
        return None
    return int(m.group(2) or m.group(1))

# Discipliner hvor TSS er et daarligt maal for gennemfoerelse. Hike/walk koeres
# bevidst i Z1 og genererer puls-baseret TSS paa ~9-20 TSS/time, mens planens
# estimat ligger langt hoejere. Resultatet var at et pas kunne ligge paa 75% af
# sin planlagte varighed og alligevel blive stemplet 'minimal' (<20% paa TSS) og
# dermed ikke markeret gennemfoert. For disse discipliner er tid det aegte maal.
# Tilfoejet 13/8-2026 efter torsdagens hike: 90 af 120 min = 18% paa TSS.
# 3/9-2026: 'strength' med — styrke giver naesten ingen TSS (ingen effekt/puls-
# zoner), saa et fuldt gennemfoert 45-min pas stod som 'minimal'. Tid er maalet.
DURATION_FIRST_DISCS = ('hike', 'walk', 'strength')

def calc_completion(actual_tss, planned_tss, actual_mins, planned_mins,
                     actual_distance_m=None, planned_distance_m=None, threshold=0.80,
                     disc=None):
    """
    Returnerer (status, pct):
      'done'    ≥80% på det SVAGESTE af de tilgængelige mål
      'partial' 20-79% på det svageste mål
      'minimal' <20% — nærmest ikke gennemført

    Rettet 7/8-2026: hvis planen har et eksplicit distance-mål (typisk svøm),
    indgår distance-pct i vurderingen sammen med TSS/tid-pct — status afgøres
    af MIN() af de tilgængelige kandidater. En session der rammer sin planlagte
    varighed men lander markant under sin planlagte distance skal ikke kunne
    fremstå 'done' uden at det er synligt. Mangler actual_distance_m (Garmin/
    Intervals har ikke rapporteret distance), ignoreres distance-kandidaten —
    det undgår falske 'minimal'-flag på rene datahuller.
    """
    pct_candidates = []

    have_tss  = bool(planned_tss  and planned_tss  > 0 and actual_tss  and actual_tss  > 0)
    have_mins = bool(planned_mins and planned_mins > 0 and actual_mins and actual_mins > 0)
    duration_first = (disc or '').lower() in DURATION_FIRST_DISCS

    if duration_first and have_mins:
        pct_candidates.append(actual_mins / planned_mins)
    elif have_tss:
        pct_candidates.append(actual_tss / planned_tss)
    elif have_mins:
        pct_candidates.append(actual_mins / planned_mins)

    if planned_distance_m and planned_distance_m > 0 and actual_distance_m is not None:
        pct_candidates.append(actual_distance_m / planned_distance_m)

    if not pct_candidates:
        return 'done', None  # matchet men ingen data overhovedet — antag done

    pct = min(pct_candidates)
    if pct >= threshold:      return 'done',    round(pct * 100)
    elif pct >= 0.20:         return 'partial', round(pct * 100)
    else:                     return 'minimal', round(pct * 100)

# Discipliner der matcher paa tvaers (7/9-2026): Garmin sender gaature som
# "Walk", men plan.json bruger "hike" til alle Gang-pas. Uden aekvivalens
# landede dagens tur som "ekstra" og det planlagte pas stod aabent.
_DISC_EQUIV = (("swim", "openwater"), ("walk", "hike"))

def _disc_equiv(a, b):
    if a == b:
        return True
    return any(a in grp and b in grp for grp in _DISC_EQUIV)


def build_week_sessions(done_map, planned_sessions):
    """Opdater done-status på ugessessioner baseret på Intervals-aktiviteter.
    done_map: {dag_short: [(disc, navn), ...]} sorteret efter tidspunkt.
    Planlagte sessioner matches mod aktiviteter af samme disc; resterende
    aktiviteter tilføjes som separate ekstra-rækker (walk, hike, commute osv.)."""
    today     = date.today()
    today_idx = today.weekday()  # 0=Man, 6=Søn

    disc_labels = {
        'run': 'Løb', 'bike': 'Cykel', 'swim': 'Svøm', 'strength': 'Styrke',
        'free': 'Aktiv restitution', 'walk': 'Gåtur', 'hike': 'Vandring',
        'commute': 'Pendling', 'openwater': 'Open water',
    }

    # Spor hvilke aktiviteter pr. dag der er brugt til at matche planlagte sessioner
    used = {day: set() for day in done_map}

    result = []
    planned_days = set()
    for s in planned_sessions:
        day_key = s['day']
        try:
            day_idx = DAY_SHORT.index(day_key)
        except:
            day_idx = -1

        planned_days.add(day_key)
        new_s = dict(s)
        new_s.pop('today', None)
        # Ekstra aktiviteter får egne rækker nu — planlagte sessioner skal ikke
        # bære en forældet disc2 (fx "free"), som gav et overflødigt FRI-tag.
        new_s.pop('disc2', None)

        if day_idx == today_idx:
            new_s['today'] = True

        if day_idx <= today_idx and day_key in done_map:
            acts = done_map[day_key]
            planned_disc = s.get('disc')
            # Kun match på korrekt disc — ingen fallback
            # Kommute/cykel må ikke forbruge et planlagt løb
            match_idx = None
            for i, act_entry in enumerate(acts):
                disc = act_entry[0]
                # Pendlingsture matcher ALDRIG et planlagt pas. En 12-min tur paa
                # 3 TSS er ikke 15% af et 80-min hometrainer-pas — den er en
                # selvstaendig ekstra-aktivitet. Den gamle regel lod commute
                # forbruge et cykel-pas hvis ingen rigtig cykeltur fandtes, og
                # gjorde dagens pas "brugt" foer det var koert.
                if i not in used[day_key] and _disc_equiv(disc, planned_disc):
                    match_idx = i
                    break
            if match_idx is not None:
                act_entry = acts[match_idx]
                act_disc, act_name, act_tss, act_dur_mins = act_entry[0], act_entry[1], act_entry[2], act_entry[3]
                act_compliance = act_entry[4] if len(act_entry) > 4 else None
                act_pace_zt    = act_entry[5] if len(act_entry) > 5 else None
                act_power_zt   = act_entry[6] if len(act_entry) > 6 else None
                act_hr_zt      = act_entry[7] if len(act_entry) > 7 else None
                act_distance_m = act_entry[9] if len(act_entry) > 9 else None
                # planned_mins/planned_tss kommer nu primært fra selve Intervals-eventet
                # (sat i get_planned_weeks() ud fra moving_time/icu_training_load) --
                # rettet 7/8-2026, det blev tidligere aldrig lagt på session-objektet,
                # så calc_completion faldt næsten altid tilbage til "ingen data, antag done".
                # parse_planned_mins() beholdes som fallback for ældre/uændrede session-objekter.
                planned_mins_val = s.get('planned_mins') or parse_planned_mins(s.get('label', ''))
                planned_tss_val  = s.get('planned_tss') or None
                planned_distance_val = s.get('planned_distance_m') or None

                status, pct = calc_completion(
                    act_tss, planned_tss_val,
                    act_dur_mins, planned_mins_val,
                    actual_distance_m=act_distance_m,
                    planned_distance_m=planned_distance_val,
                    disc=planned_disc,
                )
                new_s['completion']         = status
                new_s['completion_pct']     = pct
                new_s['actual_tss']         = act_tss
                new_s['actual_name']        = act_name   # Garmin-navn (indeholder stednavn, fx 'Fornalutx Cykling på vej')
                new_s['actual_mins']        = act_dur_mins
                new_s['planned_mins']       = planned_mins_val
                new_s['actual_distance_m']  = act_distance_m
                new_s['planned_distance_m'] = planned_distance_val
                new_s['done'] = (status in ('done', 'partial'))
                # Zone-compliance data (til dashboard og AI-coaching)
                if act_compliance and act_compliance > 0:
                    new_s['intervals_compliance'] = round(act_compliance, 1)
                used[day_key].add(match_idx)

        result.append(new_s)

    # Ekstra-pas: alle ubrugte aktiviteter tilføjes som separate rækker
    for day_key, acts in done_map.items():
        try:
            day_idx = DAY_SHORT.index(day_key)
        except:
            continue
        if day_idx > today_idx:
            continue
        for i, act_entry in enumerate(acts):
            if i in used.get(day_key, set()):
                continue
            disc, name = act_entry[0], act_entry[1]
            tss, dur_mins = act_entry[2], act_entry[3]
            label = name if name else disc_labels.get(disc, disc)
            extra = {
                'day': day_key,
                'disc': disc,
                'label': label,
                'done': True,
                'extra': True,
                # Faktiske tal skal også følge med ekstra-pas (8/8-2026), ellers
                # kan coachen kun omtale dem ved navn og gætter på omfanget.
                'actual_tss': tss,
                'actual_mins': dur_mins,
                'actual_distance_m': act_entry[9] if len(act_entry) > 9 else None,
            }
            if day_idx == today_idx:
                extra['today'] = True
            result.append(extra)

    result.sort(key=lambda s: DAY_SHORT.index(s['day']) if s['day'] in DAY_SHORT else 99)
    return result


def get_planned_weeks(weeks_back=2, weeks_ahead=6):
    """Hent planned workouts fra Intervals for et vindue omkring den aktuelle uge.
    Returnerer all_weeks dict: {week_num: {sessions: [...], focus: str, blockType: str}}

    Vinduet er aktuel uge -weeks_back .. +weeks_ahead (clampet til programmet).
    weeks_back=None og weeks_ahead=None -> hele programmet. For et 51-ugers
    program må vi ALDRIG hente alt: data.json ville eksplodere og Intervals-
    kaldet blive tungt.
    """
    week1     = PLAN_START
    today     = date.today()
    week_num  = current_week_no(today)
    w_first   = 1 if weeks_back is None else max(1, week_num - weeks_back)
    w_last    = TOTAL_WEEKS if weeks_ahead is None else min(TOTAL_WEEKS, week_num + weeks_ahead)

    # BLOCK_TYPES og DAY_SHORT kommer fra config.py (afledt af plan.json) —
    # rettet 6/8-2026. Var lokale hardkodede uge 1-14-kopier her, der stille
    # ignorerede et evt. længere/kortere aktivt program.

    TYPE_MAP = {
        'Run':'run','TrailRun':'run','VirtualRun':'run','IndoorRun':'run',
        'Ride':'bike','VirtualRide':'bike','MountainBike':'bike',
        'Cyclocross':'bike','Gravel':'bike','GravelRide':'bike',
        'Swim':'swim','OpenWaterSwim':'openwater',
        'WeightTraining':'strength','Workout':'strength','Strength':'strength',
        'Walk':'walk','Hike':'hike',
    }

    all_weeks = {}

    # Ét samlet API-kald for hele vinduet (uge w_first-w_last) i stedet for
    # individuelle kald pr. uge
    plan_start = week1 + timedelta(weeks=w_first - 1)
    plan_end   = week1 + timedelta(weeks=w_last) - timedelta(days=1)
    r = api_get(f'{BASE}/events', auth=AUTH,
                params={'oldest': str(plan_start), 'newest': str(plan_end)})
    if not r or r.status_code != 200:
        print(f"  ⚠️  get_planned_weeks: events API fejlede ({r.status_code if r else 'ingen svar'})")
        return all_weeks

    all_events = r.json()

    # Initialiser ugerne i vinduet
    for w in range(w_first, w_last + 1):
        all_weeks[w] = {'sessions': [], 'blockType': BLOCK_TYPES.get(w, 'BUILD'), 'focus': ''}

    day_order = {d:i for i,d in enumerate(DAY_SHORT)}

    for wo in all_events:
        if wo.get('category') not in ('WORKOUT', None):
            continue
        dt_str = wo.get('start_date_local', '')[:10]
        if not dt_str:
            continue
        try:
            dt = date.fromisoformat(dt_str)
        except:
            continue
        # Beregn hvilken planuge dette event tilhører
        w = _programs.week_no_raw(ACTIVE_PROGRAM, dt)
        if w not in all_weeks:
            continue
        day_idx = dt.weekday()
        disc = TYPE_MAP.get(wo.get('type',''), 'free')
        name = fix_enc(wo.get('name', 'Træning'))
        # Rettet 7/8-2026: planned_tss/planned_mins blev FØR aldrig lagt på
        # session-objektet, selvom eventet allerede bærer dem (icu_training_load
        # sat af build_workouts.py, moving_time sat direkte fra plan.json).
        # Uden dem faldt calc_completion næsten altid tilbage til "ingen data,
        # antag done". planned_distance_m er nyt: udledt af labelteksten, da
        # Intervals ikke har et separat distance-felt på planlagte events.
        _planned_secs = wo.get('moving_time') or wo.get('elapsed_time') or 0
        all_weeks[w]['sessions'].append({
            'day':   DAY_SHORT[day_idx],
            'disc':  disc,
            'label': name,
            'done':  False,
            'today': (dt == today),
            'planned_tss':        wo.get('icu_training_load') or None,
            'planned_mins':       round(_planned_secs / 60) if _planned_secs else None,
            'planned_distance_m': parse_planned_distance_m(name),
        })

    # Sorter sessions i alle uger
    for w in all_weeks:
        all_weeks[w]['sessions'].sort(key=lambda s: day_order.get(s['day'], 7))

    return all_weeks



def generate_week_focus(week_num, sessions, block_type):
    """Genererer weekFocus dynamisk fra ugens planlagte sessions i Intervals."""
    BLOCK_LABELS = {
        'BUILD': 'Build-uge', 'BUILD+': 'Intensiv build-uge',
        'RECOVERY': 'Restituitionsuge', 'TAPER': 'Taper-uge', 'RACE': 'Race-uge'
    }
    block_label = BLOCK_LABELS.get(block_type, 'Træningsuge')

    # Tæl discipliner
    discs = [s.get('disc') for s in sessions]
    runs   = discs.count('run')
    bikes  = discs.count('bike')
    swims  = discs.count('swim')
    strengths = discs.count('strength')

    parts = []
    if runs:    parts.append(f"{runs} løb")
    if bikes:   parts.append(f"{bikes} cykel")
    if swims:   parts.append(f"{swims} svøm")
    if strengths: parts.append(f"{strengths} styrke")

    discipline_str = " · ".join(parts) if parts else "aktiv hvile"

    # VO2-stimulus?
    has_vo2 = any('VO2' in (s.get('label') or '') or 'Z4' in (s.get('label') or '') or 'Z5' in (s.get('label') or '') for s in sessions)
    vo2_str = " · én VO2-stimulus" if has_vo2 else ""

    return f"{block_label} {week_num} — {discipline_str}{vo2_str}. Fokus: konsistens over intensitet."

QUOTES_TRAINING = [
    "\"Det er ikke om at have tid. Det er om at tage den.\"",
    "\"Sæt farten ned, så du kan gå langt.\"",
    "\"Konsistens slår intensitet, hver gang.\"",
    "\"Hvil er ikke det modsatte af fremskridt — det er en del af det.\"",
    "\"Formen bygges i kedsomheden — ikke i begejstringen.\"",
    "\"14 uger er lang tid. Men hver dag er kort.\"",
    "\"Den bedste træning er den, du faktisk gennemfører.\"",
    "\"Recovery er ikke pause — det er produktion.\"",
    "\"Du har gjort det 16 gange før. Kroppen kender vejen.\"",
]

QUOTES_DIET = [
    "\"Et godt måltid og en god nats søvn slår en ekstra hård træning.\"",
    "\"AF-dage er ikke et offer — de er en investering i morgendagens energi.\"",
    "\"Mindre alkohol, mere søvn — den billigste performance-boost der findes.\"",
    "\"Protein ved hvert måltid. Ingen undtagelser, ingen drama.\"",
    "\"Kroppen tror, hvad sindet siger.\"",
    "\"Vægten flytter sig ikke i dag. Men vanen gør.\"",
]

QUOTES_PHILOSOPHY = [
    "\"Disciplin er at vælge mellem hvad du vil nu, og hvad du vil mest.\"",
    "\"Det er de små valg hver dag, der bygger den store form.\"",
    "\"Keep moving forward.\"",
    "\"Du konkurrerer ikke mod andre i dag. Kun mod gårsdagens dig.\"",
    "\"Smertegrænsen flytter sig — men kun hvis du respekterer den først.\"",
    "\"Sæt målet højt, men sæt i dag realistisk.\"",
    "\"Form kommer og går. Vaner bliver.\"",
    "\"Hold roen. Hold rytmen. Hold farten.\"",
    "\"Du har magt over dit sind — ikke over yderomstændigheder. Indse det, og du finder styrke.\" — Marcus Aurelius",
    "\"Begynd ikke at handle som om du har ti tusind år at leve i.\" — Marcus Aurelius",
    "\"Hindringen for handling fremmer handlingen. Det, der står i vejen, bliver vejen.\" — Marcus Aurelius",
    "\"Det er ikke at have for lidt, der gør et menneske fattigt, men at ville have mere.\" — Seneca",
    "\"Hver morgen: jeg vågner for at gøre menneskets arbejde.\" — Marcus Aurelius",
    "\"Udholdenhed er bitter, men dens frugt er sød.\"",
    "\"Du bliver til det, du gør ofte.\"",
]


def get_swim_history():
    """Hent ugentlig svømdistance (meter) siden det aktive programs uge 1.
    Bruges til svøm-progression når programmet har et svømmemål (goals.swimMeters).
    Returnerer liste: [{week, date_str, meters, cumulative}]
    """
    week1 = PLAN_START
    today = date.today()
    oldest = str(week1)
    newest = str(today)

    r = api_get(f'{BASE}/activities', auth=AUTH,
                params={'oldest': oldest, 'newest': newest,
                        'types': 'Swim,OpenWaterSwim', 'limit': 200})
    if not r or r.status_code != 200:
        return []

    acts = r.json()
    # Gruppér pr. uge
    by_week = {}
    for a in acts:
        # Intervals.icu ignorerer 'types'-parameteren, saa filtrer selv
        if a.get('type') not in ('Swim', 'OpenWaterSwim'):
            continue
        dt_str = (a.get('start_date_local') or '')[:10]
        if not dt_str:
            continue
        try:
            dt = date.fromisoformat(dt_str)
        except:
            continue
        delta = (dt - week1).days
        if delta < 0:
            continue
        w = delta // 7 + 1
        dist_m = a.get('distance') or 0
        by_week[w] = round(by_week.get(w, 0) + dist_m, 0)

    # Byg kronologisk liste uge 1 → nu
    current_week = current_week_no(today)
    result = []
    cumulative = 0
    for w in range(1, current_week + 1):
        m = by_week.get(w, 0)
        cumulative += m
        mon = week1 + timedelta(weeks=w - 1)
        result.append({
            'week':       w,
            'date':       str(mon),
            'meters':     m,
            'cumulative': round(cumulative, 0),
        })
    return result


# generate_week_focus_ai (separat AI-kald, max_tokens 60) er fjernet 6/9-2026:
# ugefokus kommer nu fra coach v2's søndags-/mandagskørsel (coach.generate_coach_v2).
