#!/usr/bin/env python3
"""
Henter KPI-data fra Intervals.icu og opdaterer data.json + index.html.
Køres via GitHub Actions dagligt kl. 03:00 UTC.
"""
import os, re, json, base64, requests, urllib.request as _urllib_req
from datetime import date, datetime, timedelta

API_KEY    = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
GH_TOKEN   = os.environ.get('GH_TOKEN', '')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
REPO       = 'hammerbamsen/fast-as-50'
BASE       = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH       = ('API_KEY', API_KEY)

# Autoritativ uge-for-uge CTL-plan (matcher CTL_PLAN i index.html — SAMME kilde,
# må ikke afvige). Indeholder bevidste recovery-dyk, fx uge 7 (41) og uge 12 (55).
# Slutmål 60 nås i uge 14 — IKKE uge 11 (det er en tidligere fejl der gav 'Mål 60
# (uge 11)' i KPI-teksten, som er rettet til at bruge denne plan i stedet).
CTL_PLAN = [34, 36, 38, 41, 44, 43, 41, 45, 49, 53, 57, 55, 58, 60]

def ctl_plan_for_week(week_num):
    """Returnerer planlagt CTL for en given uge (1-indekseret), clamped til planens længde."""
    idx = min(max(week_num, 1), len(CTL_PLAN)) - 1
    return CTL_PLAN[idx]

def fix_enc(s):
    """Ret UTF-8 strenge der fejlagtigt er decoded som Latin-1 (fx 'LÃ¸b' → 'Løb')."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s  # Allerede korrekt

DK_DAYS   = ["Mandag","Tirsdag","Onsdag","Torsdag","Fredag","Lørdag","Søndag"]
DAY_SHORT  = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]
DK_MONTHS  = ["jan","feb","mar","apr","maj","jun","jul","aug","sep","okt","nov","dec"]

BLOCK_TYPES = {1:'BUILD',2:'BUILD+',3:'BUILD+',4:'RECOVERY',5:'BUILD',6:'BUILD',
               7:'RECOVERY',8:'BUILD',9:'BUILD',10:'BUILD+',11:'BUILD+',12:'TAPER',
               13:'TAPER',14:'RACE'}

def monday_this_week():
    today = date.today()
    return today - timedelta(days=today.weekday())

def get_fitness():
    r = requests.get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': str(date.today()), 'newest': str(date.today())})
    if r.status_code == 200 and r.json():
        d = r.json()[-1]
        ctl = round(d.get('ctl') or 0, 1)
        atl = round(d.get('atl') or 0, 1)
        tsb_raw = d.get('tsb')
        # Intervals returnerer nogle gange tsb=0 fejlagtigt — beregn selv hvis det ser forkert ud
        tsb = round(tsb_raw, 1) if (tsb_raw is not None and tsb_raw != 0) else round(ctl - atl, 1)
        return {'ctl': ctl, 'atl': atl, 'tsb': tsb}
    return None

def get_wellness_7d():
    oldest = str(date.today() - timedelta(days=7))
    newest = str(date.today())
    r = requests.get(f'{BASE}/wellness', auth=AUTH, params={'oldest': oldest, 'newest': newest})
    if r.status_code == 200:
        data = r.json()
        hrvs    = [d.get('hrv')       for d in data if d.get('hrv')]
        sleeps  = [d.get('sleepSecs') for d in data if d.get('sleepSecs')]
        weights  = [d.get('weight')    for d in data if d.get('weight')]
        fats     = [d.get('bodyFat') for d in data if d.get('bodyFat')]
        proteins = [d.get('Protein')   for d in data if d.get('Protein')]
        weight_avg = round(sum(weights)/len(weights), 1) if weights else None
        return {
            'hrv_avg':    round(sum(hrvs)/len(hrvs), 1)          if hrvs   else None,
            'sleep_avg':  round(sum(sleeps)/len(sleeps)/3600, 1) if sleeps else None,
            'weight':     round(weights[-1], 1)                  if weights else None,
            'weight_avg': weight_avg,
            'fat':        round(fats[-1], 1)                     if fats   else None,
            'protein':    round(proteins[-1], 0)                 if proteins else None,
        }
    return None

def get_history_7d():
    """Bygger 10-dages historik-arrays til sparklines live fra Intervals wellness.
    Returnerer kronologiske lister (ældste→nyeste) for vægt, HRV, søvn(t), TSB.
    Hver post er {date, v, real}: real=False for dage uden måling, hvor
    værdien er fremført fra sidste kendte (så grafen kan vises stiplet/fladt).
    """
    DAYS = 28
    LOOKBACK = 35
    oldest = str(date.today() - timedelta(days=LOOKBACK))
    newest = str(date.today())
    r = requests.get(f'{BASE}/wellness', auth=AUTH, params={'oldest': oldest, 'newest': newest})
    if r.status_code != 200:
        return None
    rows = r.json()
    by_date = {(d.get('id') or d.get('date')): d for d in rows}
    dates = [date.today() - timedelta(days=i) for i in range(DAYS - 1, -1, -1)]

    def build(getter):
        out = []
        last_val = None
        for i in range(LOOKBACK, DAYS - 1, -1):
            row = by_date.get(str(date.today() - timedelta(days=i)))
            if row:
                v = getter(row)
                if v is not None:
                    last_val = v
        for d in dates:
            row = by_date.get(str(d))
            v = getter(row) if row else None
            if v is not None:
                last_val = v
                out.append({'date': str(d), 'v': v, 'real': True})
            else:
                out.append({'date': str(d), 'v': last_val, 'real': False})
        while out and out[0]['v'] is None:
            out.pop(0)
        return out

    def w_weight(row): return round(row['weight'], 1) if row.get('weight') is not None else None
    def w_hrv(row):    return round(row['hrv'], 1) if row.get('hrv') is not None else None
    def w_sleep(row):  return round(row['sleepSecs'] / 3600, 1) if row.get('sleepSecs') is not None else None
    def w_fat(row):    return round(row['bodyFat'], 1) if row.get('bodyFat') is not None else None
    def w_tsb(row):
        if row.get('ctl') is not None and row.get('atl') is not None:
            return round(row['ctl'] - row['atl'], 1)
        if row.get('tsb') is not None:
            return round(row['tsb'], 1)
        return None

    return {
        'weightHistory': build(w_weight),
        'fatHistory':    build(w_fat),
        'hrvHistory':    build(w_hrv),
        'sleepHistory':  build(w_sleep),
        'tsbHistory':    build(w_tsb),
    }

def get_ctl_curve():
    """Bygger CTL-kurve live fra projektstart til i dag (ét punkt pr. uge).
    Viser faktisk fitnessudvikling i stedet for en hardcodet prognose.
    """
    week1 = date(2026, 6, 1)
    today = date.today()
    r = requests.get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': str(week1), 'newest': str(today)})
    if r.status_code != 200:
        return None
    rows = r.json()
    by_date = {}
    for d in rows:
        k = (d.get('id') or d.get('date') or '')[:10]
        if d.get('ctl') is not None:
            by_date[k] = round(d['ctl'], 1)
    if not by_date:
        return None
    # Ét punkt pr. uge: CTL på (eller før) hver mandag fra start til nu
    curve = []
    wk = week1
    while wk <= today:
        # find seneste kendte CTL på eller før denne uges mandag+6
        cutoff = min(wk + timedelta(days=6), today)
        candidates = [v for k, v in by_date.items() if k <= str(cutoff)]
        if candidates:
            # seneste kendte værdi op til cutoff
            latest_key = max(k for k in by_date if k <= str(cutoff))
            curve.append(by_date[latest_key])
        wk += timedelta(days=7)
    return curve if curve else None

def get_af_this_week():
    """AF-dage fra mandag denne uge.
    Returnerer (count, af_log) hvor af_log = {dato: True/False/None}
    True = AF-dag (Alkohol=0), False = ikke AF (Alkohol>0), None = ikke registreret
    """
    monday = monday_this_week()
    today  = date.today()
    r = requests.get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(today)})
    
    af_log = {}
    af_count = 0
    
    if r.status_code == 200:
        data = r.json()
        # Byg dag-for-dag log fra mandag til i dag
        wellness_by_date = {(d.get('id') or d.get('date') or '')[:10]: d for d in data}
        
        current = monday
        while current <= today:
            key = str(current)
            if key in wellness_by_date:
                alkohol = wellness_by_date[key].get('Alkohol')
                if alkohol is not None:
                    is_af = (alkohol == 0)
                    af_log[key] = is_af
                    if is_af:
                        af_count += 1
                else:
                    af_log[key] = None  # Ikke registreret
            else:
                af_log[key] = None  # Ingen wellness-entry
            current += timedelta(days=1)
        
        print(f"  AF log: {af_log}")
        return af_count, af_log
    
    return None, {}


def get_af_history():
    """Henter AF-historik uge for uge siden projektstart (2026-06-01).
    Returnerer liste af dicts: [{week: 1, done: 7, total: 7, label: 'Uge 1'}, ...]
    """
    from datetime import date, timedelta
    project_start = date(2026, 6, 1)  # Mandag uge 1
    today = date.today()
    
    # Hent al wellness siden projektstart
    r = requests.get(f"{BASE}/wellness", auth=AUTH,
                     params={"oldest": str(project_start), "newest": str(today)})
    if r.status_code != 200:
        return []
    
    wellness_data = r.json()
    wellness_by_date = {(d.get("id") or d.get("date") or "")[:10]: d for d in wellness_data}
    
    history = []
    week_start = project_start
    week_num = 1
    
    while week_start <= today:
        week_end = week_start + timedelta(days=6)
        count = 0
        days_passed = 0
        
        current = week_start
        while current <= min(week_end, today):
            key = str(current)
            alkohol = wellness_by_date.get(key, {}).get("Alkohol")
            if alkohol == 0:
                count += 1
            days_passed += 1
            current += timedelta(days=1)
        
        history.append({
            "week": week_num,
            "done": count,
            "total": days_passed,
            "label": f"Uge {week_num}"
        })
        
        week_start += timedelta(days=7)
        week_num += 1
        if week_num > 14:
            break
    
    print(f"  AF historik: {history}")
    return history


def get_full_af_log():
    """Henter dag-for-dag AF log siden projektstart til brug i af.html.
    Returnerer {dato: 0/1} hvor 0 = AF-dag, 1 = ikke AF.
    """
    project_start = date(2026, 6, 1)
    today = date.today()
    r = requests.get(f"{BASE}/wellness", auth=AUTH,
                     params={"oldest": str(project_start), "newest": str(today)})
    if r.status_code != 200:
        return {}
    wellness_by_date = {(d.get("id") or d.get("date") or "")[:10]: d for d in r.json()}
    full_log = {}
    current = project_start
    while current <= today:
        k = str(current)
        alkohol = wellness_by_date.get(k, {}).get("Alkohol")
        if alkohol is not None:
            full_log[k] = 0 if alkohol == 0 else 1
        current += timedelta(days=1)
    return full_log

def get_af_streak():
    """Beregn sammenhængende AF-streak bagud fra i dag.
    Henter 90 dages wellness og tæller AF-dage (Alkohol=0) i træk,
    startende fra i dag og gående baglæns. Stopper ved første ikke-AF-dag
    eller manglende registrering.
    """
    oldest = str(date.today() - timedelta(days=90))
    newest = str(date.today())
    r = requests.get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': oldest, 'newest': newest})
    if r.status_code != 200:
        return 0
    af_by_date = {}
    for d in r.json():
        dt = (d.get('id') or d.get('date') or '')[:10]
        val = d.get('Alkohol')
        if val is not None:
            af_by_date[dt] = val

    streak = 0
    check = date.today()
    # Hvis i dag ikke er registreret endnu, start fra i gaar
    if str(check) not in af_by_date:
        check -= timedelta(days=1)
    while True:
        k = str(check)
        if af_by_date.get(k) == 0:
            streak += 1
            check -= timedelta(days=1)
        else:
            break
    print(f"  AF streak: {streak}")
    return streak

def get_activities_week():
    """TSS, løbe-km og done-sessioner fra mandag denne uge.
    Primær kilde: /activities (importerede Garmin-aktiviteter).
    Fallback: /events med paired_activity_id — fanger workouts markeret done
    i Intervals selv om Garmin-sync er forsinket."""
    monday = monday_this_week()
    today  = date.today()
    r = requests.get(f'{BASE}/activities', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(today)})
    if r.status_code == 200:
        data = r.json()

        # Supplement: hent events med paired_activity_id for at fange
        # workouts der er markeret done i Intervals men endnu ikke synkroniseret
        # som aktiviteter fra Garmin
        r_ev = requests.get(f'{BASE}/events', auth=AUTH,
                            params={'oldest': str(monday), 'newest': str(today)})
        if r_ev.status_code == 200:
            existing_ids = {a.get('id') for a in data}
            for ev in r_ev.json():
                paired_id = ev.get('paired_activity_id') or ev.get('activity_id')
                if not paired_id or paired_id in existing_ids:
                    continue
                # Hent den pågældende aktivitet direkte
                r_act = requests.get(f'{BASE}/activities/{paired_id}', auth=AUTH)
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
            if a.get('type') in ['Ride', 'VirtualRide', 'MountainBike']
        )
        # Træningstimer per type (i minutter)
        def mins(a): return round((a.get('moving_time') or a.get('elapsed_time') or 0) / 60, 0)
        def disc_of(a):
            t = a.get('type', '')
            if t in ['Ride','VirtualRide'] and a.get('commute'): return 'commute'
            if t in ['Run','TrailRun','VirtualRun','IndoorRun']:             return 'run'
            if t in ['Ride','VirtualRide','MountainBike']:       return 'bike'
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
            elif atype in ['Ride','VirtualRide','MountainBike']:
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
            done_map.setdefault(day_key, []).append((a.get('start_date_local',''), disc, a.get('name') or atype, _tss, _dur_mins))

        # Sortér efter tidspunkt og behold disc-navne + aktivitetsnavne
        for k in done_map:
            sorted_acts = sorted(done_map[k], key=lambda x: x[0])
            done_map[k] = [(disc, name, tss, dur_mins) for _, disc, name, tss, dur_mins in sorted_acts]

        return {
            'tss_week': round(total_tss, 0),
            'run_km':   round(run_km, 1),
            'bike_km':  round(bike_km, 1),
            'train_mins': train_mins,
            'done_map': done_map,
            'raw_debug': [
                {
                    'date': a.get('start_date_local','')[:16],
                    'type': a.get('type'),
                    'name': a.get('name'),
                    'moving_min': round((a.get('moving_time') or 0)/60),
                    'distance_km': round((a.get('distance') or 0)/1000, 1),
                    'icu_training_load': a.get('icu_training_load'),
                    'training_load': a.get('training_load'),
                    'icu_power_meter': a.get('icu_power_meter'),
                    'has_heartrate': a.get('has_heartrate'),
                } for a in data
            ],
        }
    return None

def get_planned_mins_this_week():
    """Henter planlagt træningstid i minutter fra Intervals denne uge.
    Bruger moving_time (sek), ellers estimated_moving_time, ellers 0.
    """
    today  = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    r = requests.get(f'{BASE}/events', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(sunday)})
    if r.status_code != 200:
        print(f"  Planned mins API fejl: {r.status_code}")
        return 0
    events = r.json()
    print(f"  Events denne uge: {len(events)}")
    total_mins = 0
    for e in events:
        if e.get('category') not in ('WORKOUT', None):
            continue
        # Prøv alle kendte varighed-felter fra Intervals
        secs = (e.get('moving_time') or
                e.get('elapsed_time') or
                e.get('indoor_time') or
                e.get('planned_duration') or 0)
        if not secs:
            # Brug load (TSS) som proxy: 1 TSS ≈ 1 min for Z2
            load = e.get('load') or 0
            if load:
                secs = load * 60  # grov approx
        mins = secs / 60 if secs > 60 else secs  # håndter hvis allerede i min
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

    # Fallback-tabel (bruges kun hvis live-data ikke kan hentes)
    week1 = date(2026, 6, 1)
    diff  = (today - week1).days
    week_num = min(max(diff // 7 + 1, 1), 14)
    fallback = {1:383,2:460,3:466,4:167,5:511,6:490,7:546,8:186,
                9:596,10:598,11:638,12:194,13:345,14:245}.get(week_num, 400)

    r = requests.get(f'{BASE}/events', auth=AUTH,
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

def fmt(val, decimals=1):
    if val is None:
        return '—'
    return f"{val:.{decimals}f}"

def color_for(val, target, lower=True):
    if val is None:
        return '#7A6A58'
    ratio = val / target if target else 1
    if lower:
        if ratio <= 1.0:    return '#27AE60'
        elif ratio <= 1.09: return '#F39C12'
        else:               return '#C0392B'
    else:
        if ratio >= 1.0:    return '#27AE60'
        elif ratio >= 0.91: return '#F39C12'
        else:               return '#C0392B'

def gh_get(path):
    r = requests.get(f'https://api.github.com/repos/{REPO}/contents/{path}',
                     headers={'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github+json'})
    if r.status_code == 200:
        d = r.json()
        return d['sha'], base64.b64decode(d['content']).decode()
    return None, None

def gh_put(path, sha, content, message):
    r = requests.put(
        f'https://api.github.com/repos/{REPO}/contents/{path}',
        headers={'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github+json'},
        json={'message': message, 'content': base64.b64encode(content.encode()).decode(), 'sha': sha}
    )
    ok = r.status_code in (200, 201)
    print(f"  {'✅' if ok else '❌'} {path}: {r.json().get('commit',{}).get('sha','')[:7] if ok else r.text[:100]}")
    return ok

def parse_planned_mins(label):
    """Parser planlagt varighed fra label. Fx 'Lang løb Z2 90 min' → 90."""
    m = re.search(r'(\d+)\s*min', label or '', re.IGNORECASE)
    return int(m.group(1)) if m else None

def calc_completion(actual_tss, planned_tss, actual_mins, planned_mins, threshold=0.80):
    """
    Returnerer (status, pct):
      'done'    ≥80% af planlagt TSS (primær) eller tid (fallback)
      'partial' 20-79%
      'minimal' <20% — nærmest ikke gennemført
    """
    if planned_tss and planned_tss > 0 and actual_tss and actual_tss > 0:
        pct = actual_tss / planned_tss
        if pct >= threshold:      return 'done',    round(pct * 100)
        elif pct >= 0.20:         return 'partial', round(pct * 100)
        else:                     return 'minimal', round(pct * 100)
    if planned_mins and planned_mins > 0 and actual_mins and actual_mins > 0:
        pct = actual_mins / planned_mins
        if pct >= threshold:      return 'done',    round(pct * 100)
        elif pct >= 0.20:         return 'partial', round(pct * 100)
        else:                     return 'minimal', round(pct * 100)
    return 'done', None  # matchet men ingen data — antag done

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
            for i, (disc, name, act_tss, act_dur_mins) in enumerate(acts):
                if i not in used[day_key] and (disc == planned_disc or (disc == "openwater" and planned_disc == "swim")):
                    match_idx = i
                    break
            if match_idx is not None:
                act_disc, act_name, act_tss, act_dur_mins = acts[match_idx]
                planned_mins_val = parse_planned_mins(s.get('label', ''))
                planned_tss_val  = s.get('planned_tss') or None

                status, pct = calc_completion(
                    act_tss, planned_tss_val,
                    act_dur_mins, planned_mins_val
                )
                new_s['completion']     = status
                new_s['completion_pct'] = pct
                new_s['actual_tss']     = act_tss
                new_s['actual_mins']    = act_dur_mins
                new_s['planned_mins']   = planned_mins_val
                new_s['done'] = (status in ('done', 'partial'))
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
        for i, (disc, name, tss, dur_mins) in enumerate(acts):
            if i in used.get(day_key, set()):
                continue
            label = name if name else disc_labels.get(disc, disc)
            extra = {
                'day': day_key,
                'disc': disc,
                'label': label,
                'done': True,
                'extra': True,
            }
            if day_idx == today_idx:
                extra['today'] = True
            result.append(extra)

    result.sort(key=lambda s: DAY_SHORT.index(s['day']) if s['day'] in DAY_SHORT else 99)
    return result

def get_planned_weeks():
    """Hent planned workouts fra Intervals for forrige, denne og næste uge.
    Returnerer all_weeks dict: {week_num: {sessions: [...], focus: str, blockType: str}}
    """
    week1     = date(2026, 6, 1)
    today     = date.today()
    week_num  = min(max((today - week1).days // 7 + 1, 1), 14)

    BLOCK_TYPES = {1:'BUILD',2:'BUILD+',3:'BUILD+',4:'RECOVERY',5:'BUILD',6:'BUILD',
                   7:'RECOVERY',8:'BUILD',9:'BUILD',10:'BUILD+',11:'BUILD+',12:'TAPER',
                   13:'TAPER',14:'RACE'}

    TYPE_MAP = {
        'Run':'run','TrailRun':'run','VirtualRun':'run','IndoorRun':'run',
        'Ride':'bike','VirtualRide':'bike','MountainBike':'bike',
        'Swim':'swim',
        'WeightTraining':'strength','Workout':'strength','Strength':'strength',
        'Walk':'free','Hike':'free',
    }
    DAY_SHORT = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]

    all_weeks = {}

    for w in range(1, 15):  # Alle 14 uger altid

        # Beregn mandag for denne uge
        mon = week1 + timedelta(weeks=w-1)
        sun = mon + timedelta(days=6)

        r = requests.get(f'{BASE}/events', auth=AUTH,
                         params={'oldest': str(mon), 'newest': str(sun)})
        if r.status_code != 200:
            continue

        workouts = r.json()
        sessions = []
        for wo in workouts:
            # Spring over completed activities — kun planlagte WORKOUT events
            if wo.get('category') not in ('WORKOUT', None):
                continue
            dt_str = wo.get('start_date_local', '')[:10]
            if not dt_str:
                continue
            try:
                dt = date.fromisoformat(dt_str)
            except:
                continue
            day_idx = dt.weekday()  # 0=Man
            disc = TYPE_MAP.get(wo.get('type',''), 'free')
            name = fix_enc(wo.get('name', 'Træning'))
            is_today = (dt == today)
            is_done = wo.get('athlete_id') and dt <= today  # planned er ikke done

            # Tjek om der er en faktisk completed aktivitet samme dag
            sessions.append({
                'day':   DAY_SHORT[day_idx],
                'disc':  disc,
                'label': name,
                'done':  False,  # opdateres af done_map i main()
                'today': is_today,
            })

        # Sorter efter ugedag
        day_order = {d:i for i,d in enumerate(DAY_SHORT)}
        sessions.sort(key=lambda s: day_order.get(s['day'], 7))

        all_weeks[w] = {
            'sessions':  sessions,
            'blockType': BLOCK_TYPES.get(w, 'BUILD'),
            'focus':     '',  # kan tilføjes senere
        }

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


def get_travel_label(today_str):
    """Læs data/travel_days.json og returner en KORT rejse-label for i dag (eller
    None) — uden nogen antagelse om hvilken retning vægten har bevæget sig.
    Listen vedligeholdes manuelt (typisk i søndagsrutinen ud fra Outlook-
    kalenderen) — scriptet selv har ikke live kalenderadgang."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'travel_days.json')
    try:
        with open(path, encoding='utf-8') as f:
            trips = json.load(f).get('trips', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    for trip in trips:
        if trip.get('travel_home_date') == today_str:
            return trip.get('label_home') or f"dagen efter hjemrejse fra {trip.get('label', 'rejse')}"
        start, end = trip.get('start'), trip.get('end')
        if start and end and start <= today_str <= end:
            return trip.get('label_during') or f"midt i {trip.get('label', 'rejse')}"
    return None


def weight_delta_vs_recent(weight_history, today_str, weight_today):
    """Sammenlign dagens reelle vægt med seneste forudgående REELLE måling (ikke en
    fremført/fyldt værdi). Returnerer (delta, dato) eller (None, None)."""
    if weight_today is None or not weight_history:
        return None, None
    prior_real = [h for h in weight_history if h.get('real') and h.get('date') != today_str]
    if not prior_real:
        return None, None
    prior = prior_real[-1]
    if prior.get('v') is None:
        return None, None
    return round(weight_today - prior['v'], 1), prior['date']


def build_weight_context_note(travel_label, delta, prior_date, threshold=0.8):
    """Kombinerer rejse-label og FAKTISK vægt-delta til én note. Kritisk: 'sandsynligvis
    væske/retention'-sproget bruges KUN når vægten reelt er steget — en rejsedag-label
    må aldrig i sig selv få coachen til at påstå retention hvis vægten faktisk er faldet
    eller uændret. Bruges både til den hårdkodede coachSpeech og AI-prompten."""
    if delta is None:
        return None
    suffix = f", {travel_label}" if travel_label else ""
    if delta >= threshold:
        return (f"Vægten er {delta} kg højere end seneste måling ({prior_date}){suffix} — "
                f"sandsynligvis væske/natrium snarere end fedt, ikke et disciplinproblem. "
                f"Giv den et par dage før du dømmer tallet.")
    if delta <= -threshold and travel_label:
        return (f"Vægten er allerede {abs(delta)} kg lavere end seneste måling ({prior_date}) "
                f"({travel_label}) — ser ud til at have normaliseret sig hurtigt. Godt tegn.")
    return None


def build_trajectory_note(week_num, ctl, weight, weight_history):
    """Bygger en 'store billede'-sætning til den UGENTLIGE opsummering (søndage) —
    i modsætning til den daglige tekst, som kun ser på i dags snapshot, kigger denne
    på CTL-pace mod den rigtige (recovery-justerede) ugeplan og vægtens udvikling
    over de seneste uger. Returnerer None hvis der ikke er nok data."""
    parts = []

    if ctl is not None and week_num:
        plan_target = ctl_plan_for_week(week_num)
        delta = round(ctl - plan_target, 1)
        if delta >= 0:
            parts.append(f"CTL {fmt(ctl,1)} er {delta} point FORAN ugeplanen (planmål uge {week_num}: {plan_target}).")
        else:
            parts.append(f"CTL {fmt(ctl,1)} er {abs(delta)} point BAG ugeplanen (planmål uge {week_num}: {plan_target}).")

    if weight is not None and weight_history:
        reals = [h for h in weight_history if h.get('real') and h.get('v') is not None]
        if len(reals) >= 2:
            earliest = reals[0]
            try:
                days = (date.today() - date.fromisoformat(earliest['date'])).days
            except ValueError:
                days = None
            w_delta = round(weight - earliest['v'], 1)
            if days and days >= 7 and abs(w_delta) >= 0.3:
                retning = "tabt" if w_delta < 0 else "taget på"
                parts.append(f"Vægten har {retning} {abs(w_delta)} kg over de seneste {days} dage ({fmt(earliest['v'])} → {fmt(weight)} kg).")

    return " ".join(parts) if parts else None


def qa_coach_speech(speech, week_sessions, ctl, tsb, weight, af_this_week, tss_act, planned):
    """QA-tjek: returner liste af fejl hvis coach-teksten modsiger de faktiske data.
    Bruges til at stoppe en forkert tekst fra at gå live.

    Regler:
    1. Nævn aldrig en session som manglende hvis den er done=True i week_sessions
    2. Nævn aldrig VO2 som manglende hvis en Z4/Z5-session er done=True
    3. CTL/TSB/vægt-referencer skal matche de faktiske tal
    4. TSS-compliance må ikke kalde mangler hvis alle planlagte sessions er done
    """
    errors = []

    # Byg sæt af done-labels (lowercase) og done-discs
    done_labels = set()
    done_discs = set()
    all_planned_done = True
    has_vo2_done = False

    for s in (week_sessions or []):
        if s.get('extra'):
            continue  # ignorer ekstra-aktiviteter i QA
        label = (s.get('label') or '').lower()
        disc = s.get('disc', '')
        if s.get('done'):
            done_labels.add(label)
            done_discs.add(disc)
            if any(z in label for z in ['z4', 'z5', 'vo2', 'interval', 'bjerg']):
                has_vo2_done = True
        else:
            all_planned_done = False

    speech_lower = speech.lower()

    # Regel 1+2: Ingen "mangler VO2" hvis VO2 er done
    if has_vo2_done:
        for phrase in ['mangler vo2', 'kør den vo2', 'vo2-session mangler', 'mangler stadig én vo2']:
            if phrase in speech_lower:
                errors.append(f"QA FEJL: Teksten nævner manglende VO2 men en Z4/Z5-session er done=True. Fjern: '{phrase}'")

    # Regel 3: Alle planlagte sessions done — ingen "mangler sessioner"
    if all_planned_done:
        for phrase in ['sessioner står tilbage', 'mangler for at nå', 'ikke gennemført']:
            if phrase in speech_lower:
                errors.append(f"QA FEJL: Alle planlagte sessions er done men teksten antyder mangler. Fjern: '{phrase}'")

    # Regel 4: TSB-referencer skal matche faktiske tal
    if tsb is not None:
        if tsb >= -10 and 'rød zone' in speech_lower:
            errors.append(f"QA FEJL: TSB={tsb} er ikke i rød zone men teksten siger det.")
        if tsb < -30 and 'sundt niveau' in speech_lower:
            errors.append(f"QA FEJL: TSB={tsb} er under -30 (kritisk) men teksten siger 'sundt niveau'.")

    # Regel 5: Vægt-referencer skal matche
    if weight is not None:
        if weight <= 72 and 'kalder på fokus på protein' in speech_lower:
            errors.append(f"QA FEJL: Vægt={weight} er under mål (72) men teksten kalder på fokus.")

    if errors:
        print("  ⚠️  Coach QA fejl:")
        for e in errors:
            print(f"    {e}")
    else:
        print("  ✅ Coach QA: ingen fejl")

    return errors


def generate_coach_speech(week_num, weekday, streak, af_this_week, today_session, block_type, week_focus,
                           ctl=None, tsb=None, weight=None, sleep=None, compliance=None,
                           tss_act=None, planned=None, remaining_sessions=None, week_sessions=None,
                           travel_note=None, trajectory_note=None):
    """Genererer daglig coach-tekst: dagsintro + session + Friel/Martin-vurdering (godt/fokus).

    Coaching-princip: hold Kennet på sporet mod Christiansborg (29/8) og Médoc (5/9).
    - Peg ALTID fremad: hvad er næste konkrete handling
    - Nævn ALDRIG manglende sessions der faktisk er done=True
    - Vær direkte og præcis — ikke generisk motivation
    - Brug masterplanen som kontekst — TSS=0 mandag morgen er normalt, ikke et rødt flag
    """

    # Brug week_sessions (live fra Intervals) som kilden til dagens og resten af ugens plan
    # Dette er altid opdateret og matcher hvad der faktisk er i Intervals.icu
    _all_sessions = [s for s in (week_sessions or []) if not s.get('extra')]
    today_intervals = next((s for s in _all_sessions if s.get('today')), None)
    remaining_intervals = [s for s in _all_sessions if not s.get('done') and not s.get('today')]
    DK_DAYS = ['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag']
    day_name = DK_DAYS[weekday]

    BLOCK_LABELS = {'BUILD':'build-uge','BUILD+':'intensiv build-uge','RECOVERY':'restituitionsuge','TAPER':'taper-uge','RACE':'race-uge'}
    block_label = BLOCK_LABELS.get(block_type, 'træningsuge')

    # Streak-kommentar (fallback highlight)
    if streak >= 14:
        streak_comment = f"{streak} dage i træk — imponerende disciplin."
    elif streak >= 7:
        streak_comment = f"{streak} dage i træk. Hold den streak i live."
    elif streak >= 3:
        streak_comment = f"{streak} AF-dage i træk — godt momentum."
    else:
        streak_comment = f"{af_this_week}/7 AF-dage denne uge. Hvert valg tæller."

    # Tjek faktisk done-status fra week_sessions (ikke remaining_sessions der kan være stale)
    sessions_list = week_sessions or []
    planned_sessions = [s for s in sessions_list if not s.get('extra')]
    done_count = sum(1 for s in planned_sessions if s.get('done'))
    total_planned = len(planned_sessions)
    all_done = (done_count == total_planned) and total_planned > 0
    has_vo2_done = any(
        any(z in (s.get('label') or '').lower() for z in ['z4', 'z5', 'vo2', 'interval', 'bjerg'])
        for s in planned_sessions if s.get('done')
    )

    # Faktisk remaining baseret på week_sessions — ikke stale liste fra main()
    actual_remaining = [s.get('label', '') for s in planned_sessions if not s.get('done')]

    # Dagens session
    if today_session and not today_session.get('done'):
        disc = today_session.get('disc','')
        title = today_session.get('label','træning')
        disc_map = {'run':'løb','bike':'cykel','swim':'svøm','strength':'styrke','free':'aktiv restitution'}
        disc_dk = disc_map.get(disc, 'træning')
        session_line = f"I dag: {title} ({disc_dk})."
    elif today_session and today_session.get('done'):
        session_line = "Dagens session er gennemført."
    else:
        session_line = "Hviledag i dag."

    # Ugedag-intro
    if weekday == 0:  # mandag
        intro = f"Ny uge starter — uge {week_num} af 14. {block_label.capitalize()}."
    elif weekday == 4:  # fredag
        intro = f"Fredag — tre dage tilbage af uge {week_num}."
    elif weekday == 6:  # søndag
        intro = f"Søndag — afslut uge {week_num} stærkt."
    else:
        intro = f"{day_name.capitalize()} — uge {week_num} af 14."

    # --- Friel (træning) + Kreutzer (krop/AF): hvad er godt, hvad skal der fokuseres på ---
    expected_ctl = ctl_plan_for_week(week_num)  # rigtig plan m. recovery-dyk, ikke lineær tilnærmelse
    goods, focus = [], []

    if ctl is not None:
        if ctl >= expected_ctl - 1:
            goods.append(f"CTL {fmt(ctl,1)} følger ramp-kurven mod 60.")
        else:
            focus.append(f"CTL {fmt(ctl,1)} ligger lidt under kurven, så byg gradvist.")

    if tsb is not None:
        if tsb < -30:
            focus.append(f"TSB {fmt(tsb,1)} er under bundgrænsen — prioriter restitution før mere volumen.")
        elif tsb < -20:
            goods.append(f"TSB {fmt(tsb,1)} viser hård belastning, så hold øje med trætheden.")
        else:
            goods.append(f"TSB {fmt(tsb,1)} er på et sundt niveau med plads til næste belastning.")

    # TSS-compliance — kun baseret på faktisk done status
    # Mandag morgen med 0 TSS er NORMALT — der er en fuld uge foran
    is_monday_start = (weekday == 0 and (tss_act or 0) == 0)
    if compliance is not None and not is_monday_start:
        if compliance >= 90 or all_done:
            goods.append(f"{int(compliance)} procent af ugens TSS er i hus.")
        else:
            done_tss = int(tss_act or 0)
            target_tss = int(planned or 0)
            if actual_remaining:
                if len(actual_remaining) == 1:
                    rest_str = f"{actual_remaining[0]} står tilbage"
                else:
                    rest_str = f"{len(actual_remaining)} sessioner tilbage, heriblandt {', '.join(actual_remaining[:2])}"
                focus.append(f"{done_tss} af {target_tss} TSS er i hus — {rest_str}.")
            else:
                # actual_remaining er tom = alt er done, selv om compliance < 90 (TSS-afvigelse)
                goods.append(f"Alle sessioner gennemført — {int(compliance)}% af planlagt TSS.")
    elif is_monday_start and today_intervals:
        # Mandag morgen: vis hvad der er planlagt i dag direkte fra Intervals
        label = today_intervals.get('label', 'træning')
        goods.append(f"Fuld uge foran — i dag: {label}.")

    weight_aside = None
    if weight is not None:
        if weight <= 72:
            goods.append(f"Vægt på {fmt(weight)} kg er i mål.")
        elif travel_note:
            # Holdes UDENFOR goods[]/focus[] med vilje — begge lister trunkeres til
            # de første par punkter, og denne kontekst skal aldrig kunne drukne.
            # travel_note er her allerede en komplet, retnings-korrekt sætning
            # (bygget af build_weight_context_note) — tilføj ikke mere tekst der
            # kan modsige den faktiske retning.
            weight_aside = f"Vægt på {fmt(weight)} kg — {travel_note}"
        else:
            focus.append(f"Vægt på {fmt(weight)} kg — hold protein højt og undgå lette kulhydrater om aftenen.")

    if sleep is not None:
        if sleep >= 7:
            goods.append(f"Søvn på {fmt(sleep,1)} timer er solid.")
        else:
            focus.append(f"Søvn på {fmt(sleep,1)} timer er under 7-timers målet — prioriter den.")

    # AF-vurdering: relativ til gennemførte dage (weekday 0=man, 1=tirs, osv.)
    # weekday er 0-baseret, men antallet af afsluttede dage = weekday (ikke inkl. i dag)
    days_completed = weekday  # antal dage afsluttet før i dag (mandag=0, tirsdag=1, onsdag=2, ...)
    if af_this_week >= 5:
        goods.append(f"{af_this_week}/7 AF-dage — ugens mål er ramt.")
    elif weekday == 0 and af_this_week == 0:
        # Mandag morgen: ny uge startet — ingen AF-dage endnu er normalt
        goods.append(f"Ny uge med {streak} dages streak i ryggen. Hold den.")
    elif days_completed > 0 and af_this_week >= days_completed:
        # AF-dage svarer til eller overstiger antallet af afsluttede dage — på rette spor
        remaining_days = 6 - weekday  # dage tilbage inkl. i dag
        needed = max(0, 5 - af_this_week)
        if needed == 0:
            goods.append(f"{af_this_week} AF-dage hid — mål nået allerede.")
        elif needed <= remaining_days:
            goods.append(f"{af_this_week} AF-dage i {days_completed} gennemførte dage — på rette spor. {needed} mere og ugens mål er i hus.")
        else:
            focus.append(f"{af_this_week} AF-dage hidtil — {needed} mangler i {remaining_days} dage tilbage. Stram op nu.")
    else:
        # Bag kurven relativt til ugedagen
        days_completed_display = max(days_completed, 1)
        remaining_days = 6 - weekday
        needed = max(0, 5 - af_this_week)
        focus.append(f"{af_this_week} AF-dage i {days_completed_display} afsluttede dage — {needed} mangler i {remaining_days} dage tilbage.")

    if goods:
        highlight = goods[0].rstrip(".")
    else:
        highlight = streak_comment.rstrip(".")

    rest_goods = goods[1:3]
    focus_items = focus[:3]

    parts = []
    if rest_goods:
        parts.append("Godt: " + " ".join(rest_goods))
    if weight_aside:
        parts.append(weight_aside)
    if focus_items:
        parts.append("Fokus: " + " ".join(focus_items))
    elif not rest_goods and not weight_aside:
        parts.append("Alt kører efter planen — bare fortsæt.")

    # Fremadrettet linje: hvad er næste skridt mod målet?
    weeks_to_christiansborg = max(0, round((date(2026, 8, 29) - date.today()).days / 7, 0))
    if all_done and len(focus) == 0:
        closing = f"Stærk uge. {int(weeks_to_christiansborg)} uger til Christiansborg — hold sporet."
    elif all_done:
        closing = f"Alle sessioner i hus. Juster de små ting, og resten følger."
    elif len(focus) >= 3:
        closing = "Hård uge — men det er sådan formen bygges. Hold ved."
    elif len(focus) == 0:
        closing = "Alt peger den rigtige vej. Hold ilden ved — ikke sluk den."
    else:
        closing = "Keep moving forward."
    parts.append(closing)

    # Store billede — kun når trajectory_note er givet (søndage), ikke trunkeret
    if trajectory_note:
        parts.append(f"📊 Store billede: {trajectory_note}")

    # Citat — roterer mellem træning, kost og filosofi efter dag i året
    import datetime as _dt
    day_of_year = _dt.date.today().timetuple().tm_yday
    quote_pools = [QUOTES_TRAINING, QUOTES_DIET, QUOTES_PHILOSOPHY]
    pool = quote_pools[day_of_year % len(quote_pools)]
    quote = pool[day_of_year % len(pool)]
    parts.append("")
    parts.append(quote)

    guide_line = " ".join(parts)
    speech = f"{intro} {{HL}} {session_line} {guide_line}"

    return speech.strip(), highlight.strip()



def generate_ai_assessment(week_num, weekday, day_name, ctl, tsb, weight, af_this_week, af_streak,
                             week_sessions, week_focus, today_session, tss_act, planned, travel_note=None,
                             trajectory_note=None):
    """Kalder Anthropic API server-side og returnerer HTML-formateret coach-vurdering."""
    if not ANTHROPIC_KEY:
        print("  ⚠️  ANTHROPIC_API_KEY ikke sat — springer AI-vurdering over")
        return None

    ctl_target = ctl_plan_for_week(week_num)
    kpis_str = (
        f"CTL: {ctl} (uge {week_num}-mål ifølge planen: {ctl_target}), TSB: {tsb}, Vægt: {weight} kg"
        if weight else
        f"CTL: {ctl} (uge {week_num}-mål ifølge planen: {ctl_target}), TSB: {tsb}"
    )
    days_completed = weekday + 1  # afsluttede dage inkl. i dag
    af_note = (
        f"AF denne uge: {af_this_week} AF-dage ud af {days_completed} afsluttede dage "
        f"(mål: 5 AF-dage/uge), streak: {af_streak} dage. "
        f"Vurder AF-status RELATIVT til hvor mange dage der er gået i ugen — ikke absolut ift. 7. "
        f"Hvis Kennet har {af_this_week} AF-dage ud af {days_completed} afsluttede dage, er det {af_this_week}/{max(days_completed,1)}. "
        f"AF-dage handler UDELUKKENDE om alkohol — IKKE om hvilken type træning der er planlagt. "
        f"Skriv ALDRIG at en specifik træningstype 'tæller' eller 'ikke tæller' som AF-dag."
    )
    today_label = today_session.get('label', 'hviledag') if today_session else 'hviledag'
    today_done = today_session.get('done', False) if today_session else False
    today_status = "✅ GENNEMFØRT" if today_done else "⏳ IKKE FORSØGT ENDNU"
    remaining = ", ".join(
        f"{s['day']}: {s['label']}" for s in week_sessions if not s.get('done') and not s.get('today')
    ) or "ingen planlagte"
    weight_line = f"\n- Vægt: {weight} kg (seneste måling)" if weight else ""
    travel_line = (
        f"\n- VIGTIG KONTEKST om vægt: {travel_note} Brug PRÆCIS denne forklaring/retning i "
        f"'Krop & kost'-linjen i dag — gæt eller modsig den ikke. Bebrejd ALDRIG manglende "
        f"disciplin når denne kontekst er givet."
        if travel_note else ""
    )
    trajectory_line = (
        f"\n- UGENTLIGT STORE BILLEDE (kun søndage): {trajectory_note}"
        if trajectory_note else ""
    )
    fourth_line_instruction = (
        "\n4. 📊 Store billede — brug PRÆCIS tallene fra 'UGENTLIGT STORE BILLEDE' ovenfor "
        "(CTL vs. planmål, vægtudvikling over flere uger). Gæt eller genberegn intet selv."
        if trajectory_note else ""
    )

    prompt = (
        f"Du er Joel Friel-inspireret træningscoach for Kennet Hammerby, 51 år, erfaren Ironman-atlet "
        f"i et 14-ugers reset-år mod to mål: Christiansborg Rundt (2000m svøm, 29. aug) og Marathon Médoc (5. sep).\n\n"
        f"Kennet er i uge {week_num} af 14, dag {weekday + 1} af 7 ({day_name}). Filosofi: capacity-mode, ikke performance-mode. "
        f"Mål: bygge CTL fra 34 til 60 (uge 14), tabe sig til under 72 kg, 5 AF-dage/uge.\n\n"
        f"Friel-regler:\n- TSB ikke under -30\n- CTL-stigning max 5-8/uge\n"
        f"- Recovery-uge efter hård blok\n- Max 3 løbeture/uge\n\n"
        f"Aktuelle data:\n- {kpis_str}\n- {af_note}\n- Ugefokus: {week_focus[:200]}\n"
        f"- I dag: {today_label} [{today_status}]\n- Resten af ugen: {remaining}{weight_line}{travel_line}{trajectory_line}\n\n"
        f"VIGTIGT:\n- Hvis dagens session er GENNEMFØRT, skriv om den i DATID.\n"
        f"- Hvis ikke gennemført, giv konkrete råd.\n- Nævn KUN vægt hvis aktuel måling.\n\n"
        f"Giv en KORT coach-vurdering (max 4 sætninger pr. linje) opdelt i linjer med emoji-header:\n"
        f"1. 💪 Træning & load (CTL={ctl}, TSB={tsb})\n"
        f"2. ⚖️ Krop & kost\n"
        f"3. 🎯 AF-status & fokus for resten af ugen"
        f"{fourth_line_instruction}\n\n"
        f"Skriv direkte til Kennet på dansk. Vær præcis — ingen tom ros.\n"
        f"Start IKKE med en header-linje som 'Dag X af Y uger' — den tilføjes automatisk."
    )

    try:
        payload = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()

        req = _urllib_req.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01"
            }
        )
        with _urllib_req.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            text = result["content"][0]["text"]
            print(f"  ✅ AI-vurdering genereret ({len(text)} tegn)")
            return text
    except Exception as e:
        print(f"  ⚠️  AI-vurdering fejlede: {e}")
        return None

def main():
    today     = date.today()
    weekday   = today.weekday()
    week1     = date(2026, 6, 1)
    week_num  = min(max((today - week1).days // 7 + 1, 1), 14)

    print(f"=== KPI opdatering {today} (uge {week_num}) ===")

    fitness    = get_fitness()
    wellness   = get_wellness_7d()
    activities   = get_activities_week()
    planned_weeks = get_planned_weeks()
    planned    = planned_tss_this_week()
    af_days, af_log = get_af_this_week()
    af_streak = get_af_streak()
    history    = get_history_7d()
    ctl_curve  = get_ctl_curve()

    print(f"  Fitness:    {fitness}")
    print(f"  Wellness:   {wellness}")
    print(f"  Aktivitet:  {activities}")
    print(f"  AF-dage:    {af_days}")
    print(f"  Planlagt:   {planned} TSS")

    # --- Hent data.json ---
    sha_data, data_raw = gh_get('data.json')
    if not data_raw:
        print("❌ Kunne ikke hente data.json")
        return
    data = json.loads(data_raw)

    # --- Opdater meta ---
    try:
        from zoneinfo import ZoneInfo
        now_cph = datetime.now(ZoneInfo("Europe/Copenhagen"))
    except Exception:
        # Fallback hvis tzdata mangler på runner: UTC+2 (DK sommertid)
        now_cph = datetime.utcnow() + timedelta(hours=2)
    data['meta']['updated']              = now_cph.strftime("%Y-%m-%d %H:%M")
    data['meta']['dayName']              = DK_DAYS[weekday]
    data['meta']['date']                 = f"{today.day}. {DK_MONTHS[today.month-1]}"
    data['meta']['daysToMedoc']          = (date(2026, 9, 5) - today).days
    data['meta']['daysToChristiansborg'] = (date(2026, 8, 29) - today).days
    data['meta']['week']                 = week_num

    # --- KPIs ---
    weight     = wellness.get('weight')   if wellness else None

    # weight_is_today: kun True hvis Intervals har en REEL måling dateret præcis i dag
    def _weight_today(rows):
        today_str = str(date.today())
        for row in (rows or []):
            dt = (row.get('id') or row.get('date') or '')[:10]
            if dt == today_str and row.get('weight') is not None:
                return True
        return False
    _r_today = requests.get(f'{BASE}/wellness', auth=AUTH,
                            params={'oldest': str(date.today()), 'newest': str(date.today())})
    _today_rows = _r_today.json() if _r_today.status_code == 200 else []
    weight_is_today = _weight_today(_today_rows)

    # --- Rejse-/vægtudsving-kontekst: undgå at coachen bebrejder disciplin når
    # et udsving skyldes rejse (fx hjemkomst fra Mallorca) fremfor fedt — og,
    # lige så vigtigt, undgå at påstå retention hvis vægten faktisk er FALDET ---
    travel_label = get_travel_label(str(today))
    w_delta, w_prior_date = weight_delta_vs_recent(
        (history or {}).get('weightHistory', []), str(today),
        weight if weight_is_today else None
    )
    context_note = build_weight_context_note(travel_label, w_delta, w_prior_date)
    if context_note:
        print(f"  Kontekst-note (vægt): {context_note}")

    weight_avg = wellness.get('weight_avg') if wellness else None
    fat        = wellness.get('fat')        if wellness else None
    protein    = wellness.get('protein')    if wellness else None
    hrv    = wellness.get('hrv_avg') if wellness else None
    sleep  = wellness.get('sleep_avg') if wellness else None
    ctl    = fitness.get('ctl')      if fitness else None
    atl    = fitness.get('atl')      if fitness else None
    tsb    = fitness.get('tsb')      if fitness else None
    tss_act = activities.get('tss_week') if activities else None
    km_week  = activities.get('run_km')  if activities else None
    bike_km  = activities.get('bike_km') if activities else None
    done_map   = activities.get('done_map', {})    if activities else {}
    train_mins = activities.get('train_mins', {}) if activities else {}
    compliance = round(tss_act / planned * 100, 0) if tss_act else None

    # --- Ugentligt 'store billede' — kun søndage (weekday 6), så det ikke
    # drukner den daglige tekst resten af ugen. Viser CTL-pace mod den rigtige
    # ugeplan + vægtens udvikling over flere uger, ikke kun dagens snapshot. ---
    trajectory_note = None
    if weekday == 6:
        trajectory_note = build_trajectory_note(
            week_num, ctl,
            weight if weight_is_today else None,
            (history or {}).get('weightHistory', [])
        )
        if trajectory_note:
            print(f"  Store billede (søndag): {trajectory_note}")

    tss_color = color_for(compliance, 85, lower=False) if compliance else '#7A6A58'
    data['kpis'] = {
        'weight':     {'value': fmt(weight),          'unit': 'kg', 'sub': f'Mål <72 kg · snit {fmt(weight_avg)} kg' if weight_avg else 'Mål <72 kg', 'color': color_for(weight, 72, lower=True)  if weight     else '#7A6A58'},
        'fat':        {'value': fmt(fat),              'unit': '%',  'sub': 'Mål <20%',                       'color': color_for(fat, 20, lower=True)     if fat        else '#7A6A58'},
        'ctl':        {'value': fmt(ctl, 1),           'unit': '',   'sub': f'Uge {week_num}-mål {ctl_plan_for_week(week_num)} · Slutmål 60 (uge 14)', 'color': color_for(ctl, 60, lower=False)    if ctl        else '#7A6A58'},
        'tsb':        {'value': fmt(tsb, 1),           'unit': '',   'sub': ('Hård blok · CTL−ATL, frisk >0' if tsb and tsb < -10 else 'Form · CTL−ATL, frisk >0'), 'color': '#E67E22' if tsb and tsb < -10 else '#27AE60'},
        'sleep':      {'value': fmt(sleep, 1),         'unit': 't',  'sub': 'Snit 7,5t · mål 7t',            'color': '#2874A6'},
        'runKm':      {'value': fmt(km_week, 1),       'unit': 'km', 'sub': 'Mål 40+ km uge 10',             'color': color_for(km_week, 20, lower=False) if km_week   else '#7A6A58'},
        'hrv':        {'value': fmt(hrv, 1),           'unit': 'ms', 'sub': 'Snit 7d',                       'color': '#7A6A58'},
        'tssComp':    {'value': fmt(tss_act, 0) if tss_act else '0', 'unit': 'TSS',
                       'sub': f'{int(tss_act or 0)} af {int(planned)} planlagt TSS',
                       'color': tss_color},
        'bikeKm':     {'value': fmt(bike_km, 1),       'unit': 'km', 'sub': 'Cykel denne uge',                  'color': color_for(bike_km, 50, lower=False) if bike_km else '#7A6A58'},
        'afStreak':   {'value': str(af_streak),        'unit': '',   'sub': 'Dage i træk · mål 5/uge',           'color': '#59182A'},
    }

    # --- AF-dage (man–søn denne uge) ---
    data['af'] = {
        'weekDone': af_days if af_days is not None else data.get('af', {}).get('weekDone', 0),
        'target': 5,
        'streak': af_streak
    }

    # --- AF log: dag-for-dag til af.html sync (alle uger siden projektstart) ---
    full_af_log = get_full_af_log()
    if full_af_log:
        data["af_log"] = full_af_log
        print(f"  AF log (alle dage): {len(full_af_log)} dage")

    # --- AF historik: uge-for-uge siden projektstart ---
    af_history = get_af_history()
    if af_history:
        data['af_history'] = af_history

    # --- Træningstimer per type + planlagt ---
    planned_mins = get_planned_mins_this_week()
    # Altid overskriv train_mins — også ved ugestart hvor der ingen aktiviteter er endnu
    actual_total = sum(train_mins.values())
    data['train_mins'] = train_mins
    data['train_mins']['planned'] = planned_mins
    data['train_mins']['actual_total'] = round(actual_total, 0)

    # --- Week sessions med done fra Intervals ---
    # Brug friske sessions fra Intervals (med fix_enc) — ikke stale labels fra data.json
    this_week_planned = planned_weeks.get(week_num, {}).get('sessions', data.get('week_sessions', []))
    data['week_sessions'] = build_week_sessions(done_map, this_week_planned)

    # --- Historik-grafer live fra Intervals (sparklines + CTL-kurve) ---
    if history:
        if history.get('weightHistory'): data['weightHistory'] = history['weightHistory']
        if history.get('fatHistory'):    data['fatHistory']    = history['fatHistory']
        if history.get('hrvHistory'):    data['hrvHistory']    = history['hrvHistory']
        if history.get('sleepHistory'):  data['sleepHistory']  = history['sleepHistory']
        if history.get('tsbHistory'):    data['tsbHistory']    = history['tsbHistory']
        print(f"  Historik: vægt={len(history.get('weightHistory',[]))} hrv={len(history.get('hrvHistory',[]))} søvn={len(history.get('sleepHistory',[]))} tsb={len(history.get('tsbHistory',[]))} punkter")
    if ctl_curve:
        data['ctlCurve'] = ctl_curve
        print(f"  CTL-kurve: {len(ctl_curve)} ugepunkter, seneste {ctl_curve[-1]}")

    # --- all_weeks: forrige/denne/næste uge fra Intervals ---
    if planned_weeks:
        # Merge done_map ind i denne uges sessions
        this_week = planned_weeks.get(week_num, {})
        if this_week:
            this_week['sessions'] = build_week_sessions(done_map, this_week['sessions'])
            dynamic_focus = generate_week_focus(week_num, this_week.get('sessions', []), BLOCK_TYPES.get(week_num, 'BUILD'))
            this_week['focus'] = dynamic_focus
            data['weekFocus'] = dynamic_focus
        data['all_weeks'] = {str(k): v for k, v in planned_weeks.items()}

    # --- Today session ---
    today_session = next((s for s in data['week_sessions'] if s.get('today')), None)
    if today_session:
        data['today'] = {
            'discipline': today_session.get('disc', 'free'),
            'title':      today_session.get('label', ''),
            'duration':   today_session.get('duration', ''),
            'zone':       today_session.get('zone', '–'),
            'desc':       today_session.get('desc', ''),
            'completed':  today_session.get('done', False),
        }

    # --- Coach speech (genereres dagligt) ---
    block_type = data.get('blockType', 'BUILD')
    week_focus = fix_enc(data.get('weekFocus', ''))
    data['weekFocus'] = week_focus  # Gem den rettede version tilbage
    af_this_week = data.get('af', {}).get('weekDone', 0)
    # remaining_sessions beregnes nu inde i generate_coach_speech fra week_sessions
    # -- send ikke stale liste her
    coach_speech, coach_highlight = generate_coach_speech(
        week_num, weekday, af_streak, af_this_week, today_session, block_type, week_focus,
        ctl=ctl, tsb=tsb, weight=weight if weight_is_today else None, sleep=sleep, compliance=compliance,
        tss_act=tss_act, planned=planned, week_sessions=data['week_sessions'],
        travel_note=context_note, trajectory_note=trajectory_note
    )

    # --- QA: valider coach-tekst mod faktiske data inden push ---
    qa_errors = qa_coach_speech(
        coach_speech, data['week_sessions'],
        ctl=ctl, tsb=tsb, weight=weight,
        af_this_week=af_this_week, tss_act=tss_act, planned=planned
    )
    if qa_errors:
        # Behold forrige gyldige tekst -- skriv fejl til log men push ikke forkert tekst
        print(f"  Coach QA fejlede -- beholder forrige coachSpeech")
        existing_speech = data.get('coachSpeech', '')
        if existing_speech:
            coach_speech = existing_speech
            coach_highlight = data.get('coachHighlight', coach_highlight)

    data['coachSpeech']    = coach_speech
    data['coachHighlight'] = coach_highlight

    # --- AI coach-vurdering (genereres server-side, caches i data.json) ---
    ai_text = generate_ai_assessment(
        week_num, weekday, DK_DAYS[weekday],
        ctl, tsb,
        weight if weight_is_today else None,
        af_this_week, af_streak,
        data['week_sessions'], week_focus,
        today_session, tss_act, planned,
        travel_note=context_note, trajectory_note=trajectory_note
    )
    if ai_text:
        # Konverter til simpel HTML (samme logik som dashboardet)
        # Tilføj korrekt header hardcodet (forhindrer AI i at skrive forkert "Dag X af 14 uger")
        program_day = (date.today() - date(2026, 6, 1)).days + 1
        header_str = f"Dag {program_day} af 98 · {DK_DAYS[weekday]} · Uge {week_num}"
        header_html = f'<p style="margin:0 0 8px;font-family:\'Hanken Grotesk\',sans-serif;font-size:14px;line-height:1.6;color:var(--ink)"><strong>{header_str}</strong></p>'
        html_lines = [header_html]
        for line in ai_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            html_lines.append(f'<p style="margin:0 0 8px;font-family:\'Hanken Grotesk\',sans-serif;font-size:14px;line-height:1.6;color:var(--ink)">{line}</p>')
        from datetime import datetime as _dt
        data['coachAssessmentHtml'] = ''.join(html_lines)
        data['coachAssessmentTs']   = _dt.now().strftime('%H:%M')
    else:
        # Behold eksisterende hvis API fejler
        if not data.get('coachAssessmentHtml'):
            data['coachAssessmentHtml'] = ''
            data['coachAssessmentTs']   = ''

    # --- MIDLERTIDIG DEBUG: dump rå TSS-felter pr. aktivitet for at diagnosticere
    # hvorfor ugens TSS-total virker lav. Fjernes igen efter diagnose. ---
    if activities and activities.get('raw_debug'):
        data['_debug_activities_tss'] = activities['raw_debug']

    # --- Push data.json ---
    gh_put('data.json', sha_data,
           json.dumps(data, indent=2, ensure_ascii=False),
           f'KPI auto-opdatering {today}')

    # --- Opdater kpis[] i index.html ---
    sha_html, html = gh_get('index.html')
    if html:
        lines = ['kpis:[']
        kpis_list = [
            ('VÆGT',      data['kpis']['weight']),
            ('FEDT%',     data['kpis']['fat']),
            ('CTL',       data['kpis']['ctl']),
            ('TSS COMP.', {'value': fmt(compliance,0) if compliance else '—', 'unit': '%' if compliance else '', 'sub': f"Planlagt {int(planned)} TSS", 'color': color_for(compliance, 85, lower=False) if compliance else '#7A6A58'}),
            ('HRV',       data['kpis']['hrv']),
            ('LØB KM',    data['kpis']['runKm']),
        ]
        for label, k in kpis_list:
            lines.append(f'    {{label:"{label}", value:"{k["value"]}", unit:"{k["unit"]}", sub:"{k["sub"]}", color:"{k["color"]}"}},')
        lines.append('  ]')
        kpis_block = '\n'.join(lines)
        import re as _re
        html = _re.sub(r'kpis:\[[\s\S]*?\]', kpis_block, html, count=1)
        # Bump version
        now = datetime.now().strftime("%Y%m%d-%H%M")
        html = _re.sub(r'<!-- v[\d\-]+ -->', f'<!-- v{now} -->', html)
        gh_put('index.html', sha_html, html, f'KPI kpis[] opdateret {today}')

    print("=== Done ===")

if __name__ == '__main__':
    main()






