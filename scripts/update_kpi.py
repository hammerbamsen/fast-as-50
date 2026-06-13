#!/usr/bin/env python3
"""
Henter KPI-data fra Intervals.icu og opdaterer data.json + index.html.
Køres via GitHub Actions dagligt kl. 03:00 UTC.
"""
import os, re, json, base64, requests
from datetime import date, datetime, timedelta

API_KEY    = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
GH_TOKEN   = os.environ.get('GH_TOKEN', '')
REPO       = 'hammerbamsen/fast-as-50'
BASE       = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH       = ('API_KEY', API_KEY)

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
        fats     = [d.get('bodyFat')   for d in data if d.get('bodyFat')]
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
    DAYS = 10
    LOOKBACK = 20
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
    def w_tsb(row):
        if row.get('ctl') is not None and row.get('atl') is not None:
            return round(row['ctl'] - row['atl'], 1)
        if row.get('tsb') is not None:
            return round(row['tsb'], 1)
        return None

    return {
        'weightHistory': build(w_weight),
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
            print(f"    {_a.get('start_date_local','')[:16]} | {_a.get('type')} | {_a.get('name')} | moving={_a.get('moving_time')}s")
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
            done_map.setdefault(day_key, []).append((a.get('start_date_local',''), disc, a.get('name') or atype))

        # Sortér efter tidspunkt og behold disc-navne + aktivitetsnavne
        for k in done_map:
            sorted_acts = sorted(done_map[k], key=lambda x: x[0])
            done_map[k] = [(disc, name) for _, disc, name in sorted_acts]

        return {
            'tss_week': round(total_tss, 0),
            'run_km':   round(run_km, 1),
            'bike_km':  round(bike_km, 1),
            'train_mins': train_mins,
            'done_map': done_map,
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
            for i, (disc, name) in enumerate(acts):
                if i not in used[day_key] and disc == planned_disc:
                    match_idx = i
                    break
            if match_idx is not None:
                new_s['done'] = True
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
        for i, (disc, name) in enumerate(acts):
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


def generate_coach_speech(week_num, weekday, streak, af_this_week, today_session, block_type, week_focus,
                           ctl=None, tsb=None, weight=None, sleep=None, compliance=None,
                           tss_act=None, planned=None, remaining_sessions=None):
    """Genererer daglig coach-tekst: dagsintro + session + Friel/Martin-vurdering (godt/fokus)."""
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

    # Dagens session
    if today_session and not today_session.get('done'):
        disc = today_session.get('disc','')
        title = today_session.get('label','træning')
        disc_map = {'run':'løb','bike':'cykel','swim':'svøm','strength':'styrke','free':'aktiv restitution'}
        disc_dk = disc_map.get(disc, 'træning')
        session_line = f"I dag: {title} ({disc_dk})."
    elif today_session and today_session.get('done'):
        session_line = f"Dagens session er gennemført."
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
    expected_ctl = 34 + (week_num - 1) * 1.9  # rute mod CTL 60 i uge 11
    goods, focus = [], []

    if ctl is not None:
        if ctl >= expected_ctl - 1:
            goods.append(f"CTL {fmt(ctl,1)} følger ramp-kurven mod 60.")
        else:
            focus.append(f"CTL {fmt(ctl,1)} ligger lidt under kurven, så byg gradvist.")

    if tsb is not None:
        if tsb < -30:
            focus.append(f"TSB {fmt(tsb,1)} er under bundgrænsen for restitution, så prioriter restitution før mere volumen.")
        elif tsb < -20:
            goods.append(f"TSB {fmt(tsb,1)} viser hård belastning, så hold øje med trætheden.")
        else:
            goods.append(f"TSB {fmt(tsb,1)} er på et sundt niveau med plads til næste belastning.")

    if compliance is not None:
        if compliance >= 90:
            goods.append(f"{int(compliance)} procent af ugens TSS er i hus.")
        else:
            done_tss = int(tss_act or 0)
            target_tss = int(planned or 0)
            remaining = remaining_sessions or []
            if remaining:
                if len(remaining) == 1:
                    rest_str = f"{remaining[0]} står tilbage"
                else:
                    rest_str = f"{len(remaining)} sessioner står tilbage, heriblandt {', '.join(remaining[:2])}"
                focus.append(f"{done_tss} af {target_tss} TSS er i hus, og {rest_str}.")
            else:
                focus.append(f"{done_tss} af {target_tss} TSS er i hus, og resten af ugen tæller.")

    if weight is not None:
        if weight <= 72:
            goods.append(f"Vægt på {fmt(weight)} kg er i mål.")
        else:
            focus.append(f"Vægt på {fmt(weight)} kg kalder på fokus på protein og et let kalorieunderskud.")

    if sleep is not None:
        if sleep >= 7:
            goods.append(f"Søvn på {fmt(sleep,1)} timer er solid.")
        else:
            focus.append(f"Søvn på {fmt(sleep,1)} timer er under 7-timers målet, så prioriter den.")

    if af_this_week >= 5:
        goods.append(f"{af_this_week} af 7 AF-dage er i hus, og ugens mål er ramt.")
    else:
        focus.append(f"{af_this_week} af 7 AF-dage er i hus, og {5 - af_this_week} mangler for at nå ugens mål.")

    if goods:
        highlight = goods[0].rstrip(".")
    else:
        highlight = streak_comment.rstrip(".")

    # Tag op til 3 punkter af hver — som sammenhængende sætninger
    rest_goods = goods[1:3]
    focus_items = focus[:3]

    parts = []
    if rest_goods:
        parts.append("Godt: " + " ".join(rest_goods))
    if focus_items:
        parts.append("Fokus: " + " ".join(focus_items))
    elif not rest_goods:
        parts.append("Alt kører efter planen, så bare fortsæt.")

    # Afsluttende motiverende linje afhænger af balance mellem godt/fokus
    if len(focus) >= 3:
        closing = "Det er en hård uge — men det er sådan formen bygges. Hold ved."
    elif len(focus) == 0:
        closing = "Alt peger den rigtige vej. Hold ilden ved — ikke sluk den."
    else:
        closing = "Justér de små ting, og resten følger. Keep moving forward."
    parts.append(closing)

    # Citat — roterer mellem træning, kost og filosofi efter dag i året
    import datetime as _dt
    day_of_year = _dt.date.today().timetuple().tm_yday
    quote_pools = [QUOTES_TRAINING, QUOTES_DIET, QUOTES_PHILOSOPHY]
    pool = quote_pools[day_of_year % len(quote_pools)]
    quote = pool[day_of_year % len(pool)]
    parts.append("")  # mellemrum/separator før citat
    parts.append(quote)

    guide_line = " ".join(parts)

    speech = f"{intro} {{HL}} {session_line} {guide_line}"

    return speech.strip(), highlight.strip()


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

    tss_color = color_for(compliance, 85, lower=False) if compliance else '#7A6A58'
    data['kpis'] = {
        'weight':     {'value': fmt(weight),          'unit': 'kg', 'sub': f'Mål <72 kg · snit {fmt(weight_avg)} kg' if weight_avg else 'Mål <72 kg', 'color': color_for(weight, 72, lower=True)  if weight     else '#7A6A58'},
        'fat':        {'value': fmt(fat),              'unit': '%',  'sub': 'Mål <20%',                       'color': color_for(fat, 20, lower=True)     if fat        else '#7A6A58'},
        'ctl':        {'value': fmt(ctl, 1),           'unit': '',   'sub': 'Mål 60 (uge 11)',                 'color': color_for(ctl, 60, lower=False)    if ctl        else '#7A6A58'},
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
    if train_mins:
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
    remaining_sessions = [
        s.get('label', '') for s in data['week_sessions']
        if not s.get('done') and not s.get('extra')
    ]
    coach_speech, coach_highlight = generate_coach_speech(
        week_num, weekday, af_streak, af_this_week, today_session, block_type, week_focus,
        ctl=ctl, tsb=tsb, weight=weight, sleep=sleep, compliance=compliance,
        tss_act=tss_act, planned=planned, remaining_sessions=remaining_sessions
    )
    data['coachSpeech']    = coach_speech
    data['coachHighlight'] = coach_highlight

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



