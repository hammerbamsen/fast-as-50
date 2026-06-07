#!/usr/bin/env python3
"""
Henter KPI-data fra Intervals.icu og opdaterer index.html automatisk.
Køres via GitHub Actions dagligt kl. 03:00 UTC.
"""
import os, re, json, base64, requests
from datetime import date, timedelta

API_KEY     = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID  = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
GH_TOKEN    = os.environ.get('GH_TOKEN', '')
REPO        = 'hammerbamsen/Fast-as-50'
BASE        = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH        = ('API_KEY', API_KEY)

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
        hrvs    = [d.get('hrv')        for d in data if d.get('hrv')]
        sleeps  = [d.get('sleepSecs')  for d in data if d.get('sleepSecs')]
        weights = [d.get('weight')     for d in data if d.get('weight')]
        fats    = [d.get('bodyFat')    for d in data if d.get('bodyFat')]
        return {
            'hrv_avg':    round(sum(hrvs)/len(hrvs), 1)          if hrvs    else None,
            'sleep_avg':  round(sum(sleeps)/len(sleeps)/3600, 1) if sleeps  else None,
            'weight':     round(weights[-1], 1)                  if weights else None,
            'fat':        round(fats[-1], 1)                     if fats    else None,
        }
    return None

def get_activities_week():
    """TSS og løbe-km fra mandag denne uge"""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
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
        return {'tss_week': round(total_tss, 0), 'run_km': round(run_km, 1)}
    return None

def planned_tss_this_week():
    week1 = date(2026, 6, 1)
    diff  = (date.today() - week1).days
    week_num = min(max(diff // 7 + 1, 1), 14)
    planned = {1:383,2:460,3:466,4:167,5:511,6:490,7:546,8:186,
               9:596,10:598,11:638,12:194,13:345,14:245}
    return planned.get(week_num, 400)

def fmt(val, decimals=1):
    """Formatér tal til dansk format (komma som decimal)"""
    if val is None:
        return '—'
    return f"{val:.{decimals}f}".replace('.', ',')

def color_for(val, target, lower=True, ok_pct=0.03):
    """Trafiklyskode"""
    if val is None:
        return '#7A6A58'
    ratio = val / target if target else 1
    if lower:
        if ratio <= 1.0:               return '#27AE60'
        elif ratio <= 1.0 + ok_pct*3: return '#F39C12'
        else:                          return '#C0392B'
    else:
        if ratio >= 1.0:               return '#27AE60'
        elif ratio >= 1.0 - ok_pct*3: return '#F39C12'
        else:                          return '#C0392B'

def build_kpis_block(w, f, a, planned):
    weight  = w.get('weight')  if w else None
    fat     = w.get('fat')     if w else None
    hrv     = w.get('hrv_avg') if w else None
    sleep   = w.get('sleep_avg') if w else None
    ctl     = f.get('ctl')     if f else 34
    tss_act = a.get('tss_week') if a else None
    km_week = a.get('run_km')   if a else None
    compliance = round(tss_act / planned * 100, 0) if tss_act else None

    kpis = [
        {
            'label': 'VÆGT',
            'value': fmt(weight),
            'unit':  'kg',
            'sub':   'Mål <72 kg · snit 7d',
            'color': color_for(weight, 72, lower=True) if weight else '#7A6A58',
        },
        {
            'label': 'FEDT%',
            'value': fmt(fat),
            'unit':  '%',
            'sub':   'Mål <20%',
            'color': color_for(fat, 20, lower=True) if fat else '#7A6A58',
        },
        {
            'label': 'CTL',
            'value': fmt(ctl, 0),
            'unit':  '',
            'sub':   'Mål 60 (uge 11)',
            'color': color_for(ctl, 60, lower=False) if ctl else '#7A6A58',
        },
        {
            'label': 'TSS COMP.',
            'value': fmt(compliance, 0) if compliance else '—',
            'unit':  '%' if compliance else '',
            'sub':   f'Planlagt {int(planned)} TSS',
            'color': color_for(compliance, 85, lower=False) if compliance else '#7A6A58',
        },
        {
            'label': 'HRV',
            'value': fmt(hrv, 0),
            'unit':  'ms',
            'sub':   'Snit 7d',
            'color': '#2874A6',
        },
        {
            'label': 'LØB KM',
            'value': fmt(km_week, 1),
            'unit':  'km',
            'sub':   'Denne uge (man–dag)',
            'color': color_for(km_week, 20, lower=False) if km_week else '#7A6A58',
        },
    ]
    # Build JS array string
    lines = ['kpis:[']
    for k in kpis:
        lines.append(f'    {{label:"{k["label"]}", value:"{k["value"]}", unit:"{k["unit"]}", sub:"{k["sub"]}", color:"{k["color"]}"}},')
    lines.append('  ]')
    return '\n'.join(lines)

def update_html_content(html, kpis_block):
    """Erstat kpis:[...] blokken i HTML'en"""
    pattern = r'kpis:\[[\s\S]*?\]'
    new_html = re.sub(pattern, kpis_block, html, count=1)
    if new_html == html:
        print("ADVARSEL: kpis-pattern ikke fundet i HTML!")
    return new_html

def push_to_github(content):
    """Hent SHA og PUT opdateret index.html til GitHub"""
    url = f'https://api.github.com/repos/{REPO}/contents/index.html'
    headers = {
        'Authorization': f'token {GH_TOKEN}',
        'Accept': 'application/vnd.github+json',
    }
    # Hent nuværende SHA
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"Fejl ved hentning af SHA: {r.status_code} {r.text}")
        return False
    sha = r.json()['sha']

    # PUT opdateret indhold
    payload = {
        'message': f'KPI auto-opdatering {date.today()}',
        'content': base64.b64encode(content.encode()).decode(),
        'sha': sha,
    }
    r2 = requests.put(url, headers=headers, json=payload)
    if r2.status_code in (200, 201):
        print(f"GitHub opdateret: {r2.json()['commit']['sha'][:7]}")
        return True
    else:
        print(f"Fejl ved push: {r2.status_code} {r2.text}")
        return False

def main():
    print(f"Henter data fra Intervals.icu ({date.today()})...")

    fitness  = get_fitness()
    wellness = get_wellness_7d()
    activities = get_activities_week()
    planned  = planned_tss_this_week()

    print(f"  Fitness:   {fitness}")
    print(f"  Wellness:  {wellness}")
    print(f"  Aktivitet: {activities}")
    print(f"  Planlagt:  {planned} TSS")

    kpis_block = build_kpis_block(wellness, fitness, activities, planned)
    print(f"\nNyt kpis-block:\n{kpis_block}\n")

    with open('index.html', 'r', encoding='utf-8') as fh:
        html = fh.read()

    updated = update_html_content(html, kpis_block)

    # Gem lokalt (til evt. debug)
    with open('index.html', 'w', encoding='utf-8') as fh:
        fh.write(updated)

    # Push til GitHub via API
    if GH_TOKEN:
        push_to_github(updated)
    else:
        print("Ingen GH_TOKEN — springer GitHub push over")

if __name__ == '__main__':
    main()
