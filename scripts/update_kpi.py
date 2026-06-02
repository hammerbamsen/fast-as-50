#!/usr/bin/env python3
"""
Henter KPI-data fra Intervals.icu og opdaterer index.html automatisk.
Køres via GitHub Actions hver søndag kl 06:00.
"""
import os, re, json, requests
from datetime import date, timedelta

API_KEY = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
BASE = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH = ('API_KEY', API_KEY)

def get_wellness_7d():
    """Hent HRV, søvn, vægt, fedt%, AF-dage over 7 dage"""
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

    hrvs    = [d.get('hrv') for d in data if d.get('hrv')]
    weights = [d.get('weight') for d in data if d.get('weight')]
    fats    = [d.get('bodyFat') for d in data if d.get('bodyFat')]
    
    # AF-dage: dage hvor alcohol == 0 eller ikke registreret (konservativt: kun eksplicit 0)
    af_days = sum(1 for d in data if d.get('alcohol') == 0)

    return {
        'hrv_avg':  round(sum(hrvs)/len(hrvs), 1) if hrvs else None,
        'weight':   round(weights[-1], 1) if weights else None,
        'fat':      round(fats[-1], 1) if fats else None,
        'af_days':  af_days,
    }

def get_fitness():
    """Hent CTL fra wellness endpoint"""
    r = requests.get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': str(date.today()), 
                             'newest': str(date.today())})
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

def get_activities_7d():
    """Hent TSS og løbe-km for seneste 7 dage"""
    oldest = str(date.today() - timedelta(days=7))
    newest = str(date.today())
    r = requests.get(f'{BASE}/activities', auth=AUTH,
                     params={'oldest': oldest, 'newest': newest})
    if r.status_code != 200:
        return None
    
    data = r.json()
    total_tss = sum(a.get('training_load') or 0 for a in data)
    run_km = sum(
        (a.get('distance') or 0) / 1000
        for a in data
        if a.get('type') in ['Run', 'TrailRun', 'VirtualRun']
    )
    return {
        'tss_week': round(total_tss, 0),
        'run_km':   round(run_km, 1),
    }

def planned_tss_this_week():
    week1 = date(2026, 6, 1)
    diff = (date.today() - week1).days
    week_num = min(max(diff // 7 + 1, 1), 14)
    planned = {1:383,2:460,3:466,4:167,5:511,6:490,7:546,
               8:186,9:596,10:598,11:638,12:194,13:345,14:245}
    return planned.get(week_num, 400)

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

    pattern = r'const KPI = \{[\s\S]*?\};'
    updated = re.sub(pattern, new_kpi, content)

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(updated)

    print(f"KPI opdateret: {kpi}")

def main():
    print("Henter data fra Intervals.icu...")

    wellness    = get_wellness_7d()
    fitness     = get_fitness()
    activities  = get_activities_7d()
    planned     = planned_tss_this_week()

    weight      = wellness.get('weight') if wellness else None
    fat         = wellness.get('fat') if wellness else None
    hrv         = wellness.get('hrv_avg') if wellness else None
    af_days     = wellness.get('af_days') if wellness else None
    ctl         = fitness.get('ctl') if fitness else 34
    tss_actual  = activities.get('tss_week') if activities else None
    tss_comp    = round(tss_actual / planned * 100, 0) if tss_actual else None
    km_week     = activities.get('run_km') if activities else None

    kpi = {
        'weight':         weight or 'null',
        'fat':            fat or 'null',
        'ctl':            ctl or 34,
        'hrv':            hrv or 'null',
        'tss_compliance': tss_comp or 'null',
        'km_week':        km_week or 'null',
        'af_days':        af_days if af_days is not None else 'null',
    }

    update_html(kpi)
    print("Done!")

if __name__ == '__main__':
    main()
