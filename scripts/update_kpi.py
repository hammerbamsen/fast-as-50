#!/usr/bin/env python3
"""
Henter KPI-data fra Intervals.icu og opdaterer data.json + index.html.
Køres via GitHub Actions dagligt kl. 03:00 UTC.
"""
import os, re, json, base64, requests
from datetime import date, timedelta

API_KEY    = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
GH_TOKEN   = os.environ.get('GH_TOKEN', '')
REPO       = 'hammerbamsen/fast-as-50'
BASE       = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH       = ('API_KEY', API_KEY)

DK_DAYS   = ["Mandag","Tirsdag","Onsdag","Torsdag","Fredag","Lørdag","Søndag"]
DAY_SHORT  = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]
DK_MONTHS  = ["jan","feb","mar","apr","maj","jun","jul","aug","sep","okt","nov","dec"]

def monday_this_week():
    today = date.today()
    return today - timedelta(days=today.weekday())

def get_fitness():
    r = requests.get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': str(date.today()), 'newest': str(date.today())})
    if r.status_code == 200 and r.json():
        d = r.json()[-1]
        return {
            'ctl': round(d.get('ctl') or 0, 1),
            'atl': round(d.get('atl') or 0, 1),
            'tsb': round(d.get('tsb') or 0, 1),
        }
    return None

def get_wellness_7d():
    oldest = str(date.today() - timedelta(days=7))
    newest = str(date.today())
    r = requests.get(f'{BASE}/wellness', auth=AUTH, params={'oldest': oldest, 'newest': newest})
    if r.status_code == 200:
        data = r.json()
        hrvs    = [d.get('hrv')       for d in data if d.get('hrv')]
        sleeps  = [d.get('sleepSecs') for d in data if d.get('sleepSecs')]
        weights = [d.get('weight')    for d in data if d.get('weight')]
        fats    = [d.get('bodyFat')   for d in data if d.get('bodyFat')]
        return {
            'hrv_avg':   round(sum(hrvs)/len(hrvs), 1)          if hrvs   else None,
            'sleep_avg': round(sum(sleeps)/len(sleeps)/3600, 1) if sleeps else None,
            'weight':    round(weights[-1], 1)                  if weights else None,
            'fat':       round(fats[-1], 1)                     if fats   else None,
        }
    return None

def get_af_this_week():
    """AF-dage fra mandag denne uge — tæl KUN dage med eksplicit Alkohol=0 (ikke tomme dage)"""
    monday = monday_this_week()
    today  = date.today()
    r = requests.get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(today)})
    if r.status_code == 200:
        data = r.json()
        af_count = 0
        for d in data:
            alkohol = d.get('Alkohol')  # custom field, capital A
            # AF-dag = ingen alkohol registreret eller eksplicit 0
            if alkohol is not None and alkohol == 0:
                af_count += 1
        print(f"  AF raw data: {[(d.get('date'), d.get('Alkohol')) for d in data]}")
        return af_count
    return None

def get_activities_week():
    """TSS, løbe-km og done-sessioner fra mandag denne uge"""
    monday = monday_this_week()
    today  = date.today()
    r = requests.get(f'{BASE}/activities', auth=AUTH,
                     params={'oldest': str(monday), 'newest': str(today)})
    if r.status_code == 200:
        data = r.json()
        total_tss = sum(a.get('training_load') or 0 for a in data)
        run_km = sum(
            (a.get('distance') or 0) / 1000
            for a in data
            if a.get('type') in ['Run', 'TrailRun', 'VirtualRun']
        )
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
            if atype in ['Run','TrailRun','VirtualRun']:
                disc = 'run'
            elif atype in ['Ride','VirtualRide','MountainBike']:
                disc = 'bike'
            elif atype in ['Swim']:
                disc = 'swim'
            elif atype in ['WeightTraining','Workout','Strength']:
                disc = 'strength'
            else:
                disc = 'free'
            done_map.setdefault(day_key, []).append(disc)

        return {
            'tss_week': round(total_tss, 0),
            'run_km':   round(run_km, 1),
            'done_map': done_map,
        }
    return None

def planned_tss_this_week():
    week1 = date(2026, 6, 1)
    diff  = (date.today() - week1).days
    week_num = min(max(diff // 7 + 1, 1), 14)
    planned = {1:383,2:460,3:466,4:167,5:511,6:490,7:546,8:186,
               9:596,10:598,11:638,12:194,13:345,14:245}
    return planned.get(week_num, 400)

def fmt(val, decimals=1):
    if val is None:
        return '—'
    return f"{val:.{decimals}f}".replace('.', ',')

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
    """Opdater done-status på ugessessioner baseret på Intervals-aktiviteter"""
    today     = date.today()
    today_idx = today.weekday()  # 0=Man, 6=Søn

    result = []
    for s in planned_sessions:
        day_key = s['day']
        try:
            day_idx = DAY_SHORT.index(day_key)
        except:
            day_idx = -1

        new_s = dict(s)
        new_s.pop('today', None)

        # Sæt today
        if day_idx == today_idx:
            new_s['today'] = True

        # Sæt done fra Intervals hvis dagen er passeret eller i dag
        if day_idx <= today_idx and day_key in done_map:
            new_s['done'] = True
            discs = done_map[day_key]
            if len(discs) >= 2:
                new_s['disc']  = discs[0]
                new_s['disc2'] = discs[1]
            elif len(discs) == 1:
                new_s['disc'] = discs[0]

        result.append(new_s)
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
        'Run':'run','TrailRun':'run','VirtualRun':'run',
        'Ride':'bike','VirtualRide':'bike','MountainBike':'bike',
        'Swim':'swim',
        'WeightTraining':'strength','Workout':'strength','Strength':'strength',
        'Walk':'free','Hike':'free',
    }
    DAY_SHORT = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]

    all_weeks = {}

    for offset in [-1, 0, 1]:
        w = week_num + offset
        if w < 1 or w > 14:
            continue

        # Beregn mandag for denne uge
        mon = week1 + timedelta(weeks=w-1)
        sun = mon + timedelta(days=6)

        r = requests.get(f'{BASE}/workouts', auth=AUTH,
                         params={'oldest': str(mon), 'newest': str(sun)})
        if r.status_code != 200:
            continue

        workouts = r.json()
        sessions = []
        for wo in workouts:
            dt_str = wo.get('start_date_local', '')[:10]
            if not dt_str:
                continue
            try:
                dt = date.fromisoformat(dt_str)
            except:
                continue
            day_idx = dt.weekday()  # 0=Man
            disc = TYPE_MAP.get(wo.get('type',''), 'free')
            name = wo.get('name', 'Træning')
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
    af_days    = get_af_this_week()

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
    data['meta']['updated']              = str(today)
    data['meta']['dayName']              = DK_DAYS[weekday]
    data['meta']['date']                 = f"{today.day}. {DK_MONTHS[today.month-1]}"
    data['meta']['daysToMedoc']          = (date(2026, 9, 5) - today).days
    data['meta']['daysToChristiansborg'] = (date(2026, 8, 29) - today).days
    data['meta']['week']                 = week_num

    # --- KPIs ---
    weight = wellness.get('weight')  if wellness else None
    fat    = wellness.get('fat')     if wellness else None
    hrv    = wellness.get('hrv_avg') if wellness else None
    sleep  = wellness.get('sleep_avg') if wellness else None
    ctl    = fitness.get('ctl')      if fitness else None
    atl    = fitness.get('atl')      if fitness else None
    tsb    = fitness.get('tsb')      if fitness else None
    tss_act = activities.get('tss_week') if activities else None
    km_week = activities.get('run_km')   if activities else None
    done_map = activities.get('done_map', {}) if activities else {}
    compliance = round(tss_act / planned * 100, 0) if tss_act else None

    tss_color = color_for(compliance, 85, lower=False) if compliance else '#7A6A58'
    data['kpis'] = {
        'weight':     {'value': fmt(weight),          'unit': 'kg', 'sub': 'Mål <72 kg · snit 7d',          'color': color_for(weight, 72, lower=True)  if weight     else '#7A6A58'},
        'fat':        {'value': fmt(fat),              'unit': '%',  'sub': 'Mål <20%',                       'color': color_for(fat, 20, lower=True)     if fat        else '#7A6A58'},
        'ctl':        {'value': fmt(ctl, 1),           'unit': '',   'sub': 'Mål 60 (uge 11)',                 'color': color_for(ctl, 60, lower=False)    if ctl        else '#7A6A58'},
        'tsb':        {'value': fmt(tsb, 1),           'unit': '',   'sub': 'Hård blok' if tsb and tsb < -10 else 'Form', 'color': '#E67E22' if tsb and tsb < -10 else '#27AE60'},
        'sleep':      {'value': fmt(sleep, 1),         'unit': 't',  'sub': 'Snit 7,5t · mål 7t',            'color': '#2874A6'},
        'runKm':      {'value': fmt(km_week, 1),       'unit': 'km', 'sub': 'Mål 40+ km uge 10',             'color': color_for(km_week, 20, lower=False) if km_week   else '#7A6A58'},
        'hrv':        {'value': fmt(hrv, 1),           'unit': 'ms', 'sub': 'Snit 7d',                       'color': '#7A6A58'},
        'tssComp':    {'value': fmt(compliance, 0) if compliance else '—', 'unit': '%' if compliance else '',
                       'sub': f'Planlagt {int(planned)} TSS · faktisk {int(tss_act or 0)}',
                       'color': tss_color},
    }

    # --- AF-dage (man–søn denne uge) ---
    data['af'] = {
        'weekDone': af_days if af_days is not None else data.get('af', {}).get('weekDone', 0),
        'target': 5
    }

    # --- Week sessions med done fra Intervals ---
    data['week_sessions'] = build_week_sessions(done_map, data.get('week_sessions', []))

    # --- all_weeks: forrige/denne/næste uge fra Intervals ---
    if planned_weeks:
        # Merge done_map ind i denne uges sessions
        this_week = planned_weeks.get(week_num, {})
        if this_week:
            this_week['sessions'] = build_week_sessions(done_map, this_week['sessions'])
            this_week['focus'] = data.get('weekFocus', '')
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
        from datetime import datetime
        now = datetime.now().strftime("%Y%m%d-%H%M")
        html = _re.sub(r'<!-- v[\d\-]+ -->', f'<!-- v{now} -->', html)
        gh_put('index.html', sha_html, html, f'KPI kpis[] opdateret {today}')

    print("=== Done ===")

if __name__ == '__main__':
    main()

