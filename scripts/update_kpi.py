#!/usr/bin/env python3
import os, re, requests
from datetime import date, timedelta, datetime

API_KEY    = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
BASE       = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH       = ('API_KEY', API_KEY)

def week_start():
    """Mandag denne uge"""
    today = date.today()
    return today - timedelta(days=today.weekday())

def get_wellness_7d():
    oldest = str(date.today() - timedelta(days=7))
    newest = str(date.today())
    r = requests.get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': oldest, 'newest': newest})
    if r.status_code != 200:
        print(f"Wellness fejl: {r.status_code}")
        return None
    data = r.json()
    if not data:
        return None

    weights  = [d.get('weight')  for d in data if d.get('weight')]
    fats     = [d.get('bodyFat') for d in data if d.get('bodyFat')]
    hrvs     = [d.get('hrv')     for d in data if d.get('hrv')]
    ctls     = [d.get('ctl')     for d in data if d.get('ctl')]
    sleeps   = [d.get('sleepSecs') for d in data if d.get('sleepSecs')]
    alcohols = [d.get('Alkohol') for d in data]

    # AF-dage kun fra denne uge (mandag til i dag)
    wstart = week_start()
    af_days = sum(
        1 for d in data
        if date.fromisoformat(d['id']) >= wstart
        and d.get('Alkohol') is not None
        and d.get('Alkohol') == 0
    )

    return {
        'weight':     round(weights[-1], 1)          if weights else None,
        'fat':        round(fats[-1], 1)              if fats    else None,
        'hrv_avg':    round(sum(hrvs)/len(hrvs), 1)   if hrvs    else None,
        'ctl':        round(ctls[-1], 1)              if ctls    else None,
        'sleep_avg':  round(sum(sleeps)/len(sleeps)/3600, 1) if sleeps else None,
        'af_days':    af_days,
    }

def get_activities_week():
    """Kun aktiviteter fra mandag denne uge"""
    oldest = str(week_start())
    newest = str(date.today())
    r = requests.get(f'{BASE}/activities', auth=AUTH,
                     params={'oldest': oldest, 'newest': newest})
    if r.status_code != 200:
        print(f"Activities fejl: {r.status_code}")
        return None
    data = r.json()
    total_tss = sum(a.get('training_load') or 0 for a in data)
    run_km = sum(
        (a.get('distance') or 0) / 1000
        for a in data
        if a.get('type') in ['Run', 'TrailRun', 'VirtualRun']
    )
    print(f"Uge aktiviteter: {len(data)}, TSS: {total_tss}, Løb km: {run_km}")
    return {'tss_week': round(total_tss), 'run_km': round(run_km, 1)}

def planned_tss():
    week1 = date(2026, 6, 1)
    wk = min(max((date.today() - week1).days // 7 + 1, 1), 14)
    planned = {1:383,2:460,3:466,4:167,5:511,6:490,7:546,
               8:186,9:596,10:598,11:638,12:194,13:345,14:245}
    return planned.get(wk, 400)

def update_html(kpi):
    with open('index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    new_kpi = f"""const KPI = {{
  weight: {{val: {kpi['weight']}, target: 72, unit: 'kg', lower: true}},
  fat: {{val: {kpi['fat']}, target: 20, unit: '%', lower: true}},
  ctl: {{val: {kpi['ctl']}, target: 60, unit: '', lower: false}},
  hrv: {{val: {kpi['hrv']}, target: null, unit: 'ms', lower: false}},
  tss_compliance: {{val: {kpi['tss_compliance']}, target: 85, unit: '%', lower: false}},
  km_week: {{val: {kpi['km_week']}, target: 40, unit: 'km', lower: false}},
  af_days: {{val: {kpi['af_days']}, target: 5, unit: 'dage', lower: false}},
}};"""
    updated = re.sub(r'const KPI = \{[\s\S]*?\};', new_kpi, content)
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(updated)
    print(f"KPI opdateret: {kpi}")

def main():
    print("Henter data...")
    wellness   = get_wellness_7d()
    activities = get_activities_week()
    planned    = planned_tss()

    tss_actual = activities.get('tss_week') if activities else None
    tss_comp   = round(tss_actual / planned * 100) if tss_actual else None

    kpi = {
        'weight':         (wellness.get('weight')   if wellness else None) or 'null',
        'fat':            (wellness.get('fat')       if wellness else None) or 'null',
        'ctl':            (wellness.get('ctl')       if wellness else None) or 34,
        'hrv':            (wellness.get('hrv_avg')   if wellness else None) or 'null',
        'tss_compliance': tss_comp or 'null',
        'km_week':        (activities.get('run_km')  if activities else None) or 'null',
        'af_days':        wellness.get('af_days')    if wellness else 'null',
    }
    if kpi['af_days'] is None:
        kpi['af_days'] = 'null'

    update_html(kpi)

if __name__ == '__main__':
    main()
