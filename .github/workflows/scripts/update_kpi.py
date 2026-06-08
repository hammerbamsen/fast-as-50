#!/usr/bin/env python3
"""
Henter KPI-data fra Intervals.icu og opdaterer data.json automatisk.
Kører via GitHub Actions hvert 10 min.
"""
import os, json, requests
from datetime import date, timedelta

API_KEY     = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID  = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
BASE        = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH        = ('API_KEY', API_KEY)

# Intervals.icu sport_type → dashboard disc
SPORT_TO_DISC = {
    'Run':          'run',
    'TrailRun':     'run',
    'VirtualRun':   'run',
    'Ride':         'bike',
    'VirtualRide':  'bike',
    'MountainBike': 'bike',
    'Swim':         'swim',
    'OpenWaterSwim':'openwater',
    'Walk':         'walk',
    'Hike':         'hike',
    'WeightTraining':'strength',
    'Workout':      'strength',
    'Yoga':         'strength',
}

DK_DAYS = ['Man', 'Tir', 'Ons', 'Tor', 'Fre', 'Lør', 'Søn']

def sport_to_disc(activity):
    """Map Intervals.icu activity til disc type — håndterer commute separat."""
    t = activity.get('type', '')
    if t in ('Ride', 'VirtualRide') and activity.get('commute'):
        return 'commute'
    return SPORT_TO_DISC.get(t, 'free')

def get_fitness():
    r = requests.get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': str(date.today()), 'newest': str(date.today())})
    if r.status_code == 200:
        data = r.json()
        if data:
            d = data[-1]
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
            'hrv_avg':    round(sum(hrvs)/len(hrvs), 1)         if hrvs    else None,
            'sleep_avg':  round(sum(sleeps)/len(sleeps)/3600,1) if sleeps  else None,
            'weight':     round(weights[-1], 1)                  if weights else None,
            'body_fat':   round(fats[-1], 1)                     if fats    else None,
        }
    return None

def get_activities_7d():
    oldest = str(date.today() - timedelta(days=7))
    newest = str(date.today())
    r = requests.get(f'{BASE}/activities', auth=AUTH, params={'oldest': oldest, 'newest': newest})
    if r.status_code == 200:
        data = r.json()
        total_tss = sum(a.get('training_load') or 0 for a in data)
        run_km = sum(
            (a.get('distance') or 0) / 1000
            for a in data
            if a.get('type') in ['Run', 'TrailRun', 'VirtualRun']
        )
        return {'tss_week': round(total_tss, 0), 'run_km': round(run_km, 1)}
    return None

def get_week_sessions():
    """
    Hent faktiske aktiviteter denne uge fra Intervals.icu og byg week_sessions.
    Merger planlagte (fra all_weeks) med udførte aktiviteter.
    Aktiviteter uden match på planlagt session tilføjes som bonus-sessioner.
    """
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    r = requests.get(
        f'{BASE}/activities',
        auth=AUTH,
        params={'oldest': str(monday), 'newest': str(sunday)}
    )
    if r.status_code != 200:
        return None

    activities = r.json()

    # Byg faktiske sessioner grupperet pr. dag
    # Én aktivitet = én session
    sessions = []
    for a in activities:
        act_date = a.get('start_date_local', '')[:10]
        try:
            d = date.fromisoformat(act_date)
        except Exception:
            continue
        day_label = DK_DAYS[d.weekday()]
        disc = sport_to_disc(a)
        name = a.get('name') or a.get('type') or 'Session'
        dur_secs = a.get('moving_time') or a.get('elapsed_time') or 0
        dur_min = round(dur_secs / 60)
        dur_str = f'{dur_min} min' if dur_min else ''
        tss = round(a.get('training_load') or 0)

        sessions.append({
            'day':   day_label,
            'disc':  disc,
            'label': name,
            'done':  True,
            'dur':   dur_str,
            'tss':   tss,
        })

    # Sorter man→søn
    day_order = {d: i for i, d in enumerate(DK_DAYS)}
    sessions.sort(key=lambda s: day_order.get(s['day'], 9))

    return sessions if sessions else None

def get_af_streak_and_log():
    """
    Hent Alkohol-felt fra Intervals.icu wellness for de seneste 90 dage.
    alkohol=0 = AF-dag, alkohol=1 = ikke AF-dag.
    """
    oldest = str(date.today() - timedelta(days=90))
    newest = str(date.today())
    r = requests.get(f'{BASE}/wellness', auth=AUTH, params={'oldest': oldest, 'newest': newest})
    
    streak = 0
    af_log = {}
    week_af_count = 0

    if r.status_code == 200:
        data = r.json()
        af_by_date = {}
        for d in data:
            dt = d.get('date', '')[:10]
            val = d.get('Alkohol')
            if val is not None:
                af_by_date[dt] = val

        today = date.today()
        check = today - timedelta(days=1)
        while True:
            k = str(check)
            if k not in af_by_date:
                break
            if af_by_date[k] == 0:
                streak += 1
                check -= timedelta(days=1)
            else:
                break
        
        today_str = str(today)
        if af_by_date.get(today_str) == 0:
            streak += 1

        monday = today - timedelta(days=today.weekday())
        for i in range(7):
            d = monday + timedelta(days=i)
            k = str(d)
            if k > today_str:
                break
            if k in af_by_date:
                af_log[k] = af_by_date[k]
        
        week_af_count = sum(1 for v in af_log.values() if v == 0)

    return streak, af_log, week_af_count

def planned_tss_this_week():
    week1   = date(2026, 6, 1)
    today   = date.today()
    diff    = (today - week1).days
    week_num = min(max(diff // 7 + 1, 1), 14)
    planned = {1:383,2:460,3:466,4:167,5:511,6:490,7:546,8:186,9:596,10:598,11:638,12:194,13:345,14:245}
    return planned.get(week_num, 400)

def week_meta():
    week1    = date(2026, 6, 1)
    today    = date.today()
    diff     = (today - week1).days
    week_num = min(max(diff // 7 + 1, 1), 14)
    medoc    = date(2026, 9, 5)
    cb       = date(2026, 8, 29)
    blocks   = {1:'BUILD',2:'BUILD',3:'BUILD',4:'RECOVERY',5:'BUILD',6:'BUILD',7:'BUILD',
                8:'RECOVERY',9:'BUILD',10:'BUILD',11:'BUILD',12:'RECOVERY',13:'BUILD',14:'TAPER'}
    dk_days  = ['Mandag','Tirsdag','Onsdag','Torsdag','Fredag','Lørdag','Søndag']
    dk_months= ['jan','feb','mar','apr','maj','jun','jul','aug','sep','okt','nov','dec']
    return {
        'updated':            str(today),
        'week':               week_num,
        'totalWeeks':         14,
        'blockType':          blocks.get(week_num, 'BUILD'),
        'daysToMedoc':        (medoc - today).days,
        'daysToChristiansborg': (cb - today).days,
        'dayName':            dk_days[today.weekday()],
        'date':               f"{today.day}. {dk_months[today.month-1]}",
    }

def main():
    print("Henter data fra Intervals.icu...")

    fitness    = get_fitness()
    wellness   = get_wellness_7d()
    activities = get_activities_7d()
    planned    = planned_tss_this_week()
    af_streak, af_log, week_af_count = get_af_streak_and_log()
    meta       = week_meta()
    week_sessions = get_week_sessions()

    weight  = wellness.get('weight')   if wellness else None
    fat     = wellness.get('body_fat') if wellness else None
    ctl     = fitness.get('ctl')       if fitness  else 34
    tsb     = fitness.get('tsb')       if fitness  else 0
    hrv     = wellness.get('hrv_avg')  if wellness else None
    sleep   = wellness.get('sleep_avg')if wellness else None
    tss_actual = activities.get('tss_week') if activities else None
    tss_comp   = round(tss_actual / planned * 100, 0) if tss_actual else None
    run_km     = activities.get('run_km')   if activities else None

    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            existing = json.load(f)
    except Exception:
        existing = {}

    existing['meta'] = meta
    existing['af'] = {
        'weekDone':   week_af_count,
        'target':     5,
        'streak':     af_streak,
    }
    existing['af_log'] = af_log

    # Opdater week_sessions fra faktiske Intervals-aktiviteter
    if week_sessions is not None:
        existing['week_sessions'] = week_sessions
        print(f"week_sessions opdateret: {len(week_sessions)} aktiviteter fra Intervals")
    else:
        print("Ingen aktiviteter denne uge endnu — bevarer eksisterende week_sessions")

    kpis = existing.get('kpis', {})
    def col(val, target, lower=True):
        if val is None: return '#7A6A58'
        if lower: return '#27AE60' if val <= target else ('#F39C12' if val <= target*1.05 else '#C0392B')
        else:     return '#27AE60' if val >= target else ('#F39C12' if val >= target*0.9  else '#C0392B')

    if weight:
        kpis['weight'] = {'value': str(weight).replace('.',','), 'unit': 'kg',
                          'sub': 'Mål <72 kg · snit 7d', 'color': col(weight, 72)}
    if fat:
        kpis['fat'] = {'value': str(fat).replace('.',','), 'unit': '%',
                       'sub': 'Mål <20%', 'color': col(fat, 20)}
    if ctl is not None:
        kpis['ctl'] = {'value': str(ctl).replace('.',','), 'unit': '',
                       'sub': 'Mål 60 (uge 11)', 'color': col(ctl, 60, lower=False)}
    if tsb is not None:
        kpis['tsb'] = {'value': str(tsb).replace('.',','), 'unit': '',
                       'sub': 'Form', 'color': '#27AE60' if tsb >= -10 else '#C0392B'}
    if sleep:
        kpis['sleep'] = {'value': str(sleep).replace('.',','), 'unit': 't',
                         'sub': 'Snit 7,5t · mål 7t', 'color': col(sleep, 7, lower=False)}
    if run_km:
        kpis['runKm'] = {'value': str(run_km).replace('.',','), 'unit': 'km',
                         'sub': 'Mål 40+ km uge 10', 'color': col(run_km, 40, lower=False)}
    if hrv:
        kpis['hrv'] = {'value': str(hrv).replace('.',','), 'unit': 'ms',
                       'sub': 'Snit 7d', 'color': '#7A6A58'}

    kpis['afStreak'] = {
        'value': str(af_streak),
        'unit': 'dage',
        'sub': f'AF-streak · {week_af_count}/5 denne uge',
        'color': '#27AE60' if af_streak >= 3 else '#F39C12',
    }

    existing['kpis'] = kpis

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"Done! AF streak={af_streak}, uge={week_af_count}/5, CTL={ctl}, vægt={weight}")

if __name__ == '__main__':
    main()
