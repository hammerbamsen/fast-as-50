#!/usr/bin/env python3
import os, re, requests, json
from datetime import date, timedelta

API_KEY    = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
BASE       = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH       = ('API_KEY', API_KEY)

def get_wellness_7d():
    oldest = str(date.today() - timedelta(days=7))
    newest = str(date.today())
    r = requests.get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': oldest, 'newest': newest})
    print(f"Wellness status: {r.status_code}")
    if r.status_code != 200:
        print(f"Wellness fejl: {r.text[:200]}")
        return None
    data = r.json()
    print(f"Wellness dage: {len(data)}")
    if data:
        print(f"Wellness felter: {list(data[-1].keys())}")
        print(f"Seneste dag: {json.dumps(data[-1], indent=2)[:500]}")

    # Try multiple field name variants
    weight_fields = ['weight', 'Weight', 'weight_kg']
    fat_fields    = ['bodyFat', 'body_fat', 'fatPercent', 'fat', 'bodyFatPercent']
    hrv_fields    = ['hrv', 'hrvRmssd', 'hrv4t', 'rmssd']
    alcohol_fields= ['alcohol', 'Alcohol', 'alcoholUnits']

    def get_field(d, fields):
        for f in fields:
            if d.get(f) is not None:
                return d[f]
        return None

    weights  = [get_field(d, weight_fields) for d in data if get_field(d, weight_fields)]
    fats     = [get_field(d, fat_fields)    for d in data if get_field(d, fat_fields)]
    hrvs     = [get_field(d, hrv_fields)    for d in data if get_field(d, hrv_fields)]
    alcohols = [get_field(d, alcohol_fields) for d in data]

    af_days = sum(1 for a in alcohols if a is not None and a == 0)

    return {
        'weight':  round(weights[-1], 1)          if weights else None,
        'fat':     round(fats[-1], 1)              if fats    else None,
        'hrv_avg': round(sum(hrvs)/len(hrvs), 1)   if hrvs    else None,
        'af_days': af_days,
    }

def get_fitness():
    # Try fitness endpoint directly
    r = requests.get(f'{BASE}/fitness', auth=AUTH)
    print(f"Fitness status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Fitness data: {json.dumps(data)[:300]}")
        ctl = data.get('ctl') or data.get('fitness') or data.get('CTL')
        if ctl:
            return {'ctl': round(float(ctl), 1)}

    # Fallback: wellness endpoint for today
    r2 = requests.get(f'{BASE}/wellness', auth=AUTH,
                      params={'oldest': str(date.today()), 'newest': str(date.today())})
    if r2.status_code == 200:
        data = r2.json()
        if data:
            d = data[-1]
            ctl = d.get('ctl') or d.get('fitness')
            if ctl:
                return {'ctl': round(float(ctl), 1)}
    return None

def get_activities_7d():
    oldest = str(date.today() - timedelta(days=7))
    r = requests.get(f'{BASE}/activities', auth=AUTH,
                     params={'oldest': oldest, 'newest': str(date.today())})
    print(f"Activities status: {r.status_code}")
    if r.status_code != 200:
        return None
    data = r.json()
    print(f"Activities: {len(data)}")
    if data:
        print(f"Activity felter: {list(data[0].keys())[:15]}")

    # Try multiple TSS field names
    tss_fields = ['training_load', 'tss', 'TSS', 'load']
    def get_tss(a):
        for f in tss_fields:
            if a.get(f) is not None:
                return a[f]
        return 0

    total_tss = sum(get_tss(a) for a in data)
    run_types = ['Run','TrailRun','VirtualRun','run']
    run_km = sum(
        (a.get('distance') or a.get('distanceMeters') or 0) / 1000
        for a in data
        if a.get('type') in run_types
    )
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
    print("Henter data fra Intervals.icu...")
    wellness   = get_wellness_7d()
    fitness    = get_fitness()
    activities = get_activities_7d()
    planned    = planned_tss()

    tss_actual = activities.get('tss_week') if activities else None
    tss_comp   = round(tss_actual / planned * 100) if tss_actual else None

    kpi = {
        'weight':         (wellness.get('weight')  if wellness else None) or 'null',
        'fat':            (wellness.get('fat')      if wellness else None) or 'null',
        'ctl':            (fitness.get('ctl')       if fitness  else None) or 34,
        'hrv':            (wellness.get('hrv_avg')  if wellness else None) or 'null',
        'tss_compliance': tss_comp or 'null',
        'km_week':        (activities.get('run_km') if activities else None) or 'null',
        'af_days':        (wellness.get('af_days')  if wellness else None),
    }
    if kpi['af_days'] is None:
        kpi['af_days'] = 'null'

    update_html(kpi)

if __name__ == '__main__':
    main()
