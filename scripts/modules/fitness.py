"""Fitness, wellness og historik fra Intervals.icu."""
from datetime import date, timedelta
from .config import BASE, AUTH, api_get


def get_fitness():
    r = api_get(f'{BASE}/wellness', auth=AUTH,
                     params={'oldest': str(date.today()), 'newest': str(date.today())})
    if r and r.status_code == 200 and r.json():
        d = r.json()[-1]
        ctl = round(d.get('ctl') or 0, 1)
        atl = round(d.get('atl') or 0, 1)
        tsb_raw = d.get('tsb')
        tsb = round(tsb_raw, 1) if (tsb_raw is not None and tsb_raw != 0) else round(ctl - atl, 1)
        return {'ctl': ctl, 'atl': atl, 'tsb': tsb}
    return None


def get_wellness_7d():
    oldest = str(date.today() - timedelta(days=7))
    newest = str(date.today())
    r = api_get(f'{BASE}/wellness', auth=AUTH, params={'oldest': oldest, 'newest': newest})
    if r and r.status_code == 200:
        data = r.json()
        print(f"  [DEBUG] wellness_7d: HTTP 200, {len(data)} rækker")
        if data:
            print(f"  [DEBUG] Første element keys: {list(data[0].keys())[:20]}")
            print(f"  [DEBUG] Første element: {str(data[0])[:300]}")
        hrvs    = [d.get('hrv')       for d in data if d.get('hrv')]
        sleeps  = [d.get('sleepSecs') for d in data if d.get('sleepSecs')]
        weights = [d.get('weight')    for d in data if d.get('weight')]
        fats    = [d.get('bodyFat')   for d in data if d.get('bodyFat')]
        proteins= [d.get('protein')   for d in data if d.get('protein')]  # lille p — API-navn, ikke UI-navn
        def _round1(v):
            import decimal
            return float(decimal.Decimal(str(v)).quantize(decimal.Decimal('0.1'), rounding=decimal.ROUND_HALF_UP))
        weight_avg = _round1(sum(weights)/len(weights)) if weights else None
        return {
            'hrv_avg':    round(sum(hrvs)/len(hrvs), 1)          if hrvs   else None,
            'hrv':        round(hrvs[-1], 1)                     if hrvs   else None,
            'sleep_avg':  round(sum(sleeps)/len(sleeps)/3600, 1) if sleeps else None,
            'weight':     _round1(weights[-1])                   if weights else None,
            'weight_avg': weight_avg,
            'fat':        round(fats[-1], 1)                     if fats   else None,
            'protein':    round(proteins[-1], 0)                 if proteins else None,
        }
    return None


def get_history(existing=None):
    """Fuld historik: hent hele 90-dages vinduet fra Intervals og byg efter DATO.

    Erstatter den tidligere inkrementelle get_history_7d(), som kun hentede 7
    dage og fletted dem ind i en positionsbaseret cache. Cachen blev aldrig
    rykket ved dagsskifte, så kun de sidste ~8 pladser blev opdateret; alt
    ældre frøs fast og mellemliggende dage blev overskrevet og tabt
    (verificeret hul: 22/6-9/7 2026). Ingen cache => ingen drift.

    `existing` er beholdt for bagudkompatibilitet, men bruges ikke.

    Returnerer None ved API-fejl eller tomt svar -- ALDRIG lister af None.
    Kaldsstedet i update_kpi.py tjekker truthiness, og en liste af 90 None er
    truthy: at returnere den ville overskrive god historik med nuller.
    """
    from datetime import date, timedelta
    DAYS   = 90
    today  = date.today()
    oldest = str(today - timedelta(days=DAYS - 1))
    newest = str(today)

    r = api_get(f'{BASE}/wellness', auth=AUTH, params={'oldest': oldest, 'newest': newest})
    if not r or r.status_code != 200:
        print(f"  history: API-fejl ({getattr(r, 'status_code', 'intet svar')}) -- beholder eksisterende historik")
        return None

    rows = r.json()
    if not rows:
        print("  history: tomt svar fra API -- beholder eksisterende historik")
        return None
    print(f"  history: {len(rows)} raekker fra API ({oldest} -> {newest})")

    daily = {}
    for row in rows:
        # Intervals bruger 'id'-feltet som dato (YYYY-MM-DD), ikke 'date'
        d = (row.get('id') or row.get('date') or '')[:10]
        if not d:
            continue
        ctl = row.get('ctl')
        atl = row.get('atl')
        tsb = row.get('tsb')
        # 'is not None' -- ikke truthiness: CTL/ATL/TSB kan lovligt vaere 0
        if ctl is not None and atl is not None:
            tsb_val = round(ctl - atl, 1)
        elif tsb is not None:
            tsb_val = round(tsb, 1)
        else:
            tsb_val = None
        s = row.get('sleepSecs')
        daily[d] = {
            'weight': round(row['weight'], 1)  if row.get('weight')  is not None else None,
            'fat':    round(row['bodyFat'], 1) if row.get('bodyFat') is not None else None,
            'hrv':    round(row['hrv'], 1)     if row.get('hrv')     is not None else None,
            'sleep':  round(s / 3600, 1)       if s                             else None,
            'tsb':    tsb_val,
        }

    dates = [str(today - timedelta(days=i)) for i in range(DAYS - 1, -1, -1)]

    def build(field):
        out = []
        for d_str in dates:
            v = daily.get(d_str, {}).get(field)
            out.append({'date': d_str, 'v': v, 'real': True} if v is not None else None)
        return out

    result = {
        'weightHistory': build('weight'),
        'fatHistory':    build('fat'),
        'hrvHistory':    build('hrv'),
        'sleepHistory':  build('sleep'),
        'tsbHistory':    build('tsb'),
    }
    for k, v in result.items():
        print(f"    {k}: {sum(1 for x in v if x)} af {DAYS} dage med maaling")
    return result


def get_ctl_curve():
    """Bygger CTL-kurve live fra projektstart til i dag (ét punkt pr. uge)."""
    from datetime import date, timedelta
    week1   = date(2026, 6, 1)
    today   = date.today()
    oldest  = str(week1)
    newest  = str(today)
    r = api_get(f'{BASE}/wellness', auth=AUTH, params={'oldest': oldest, 'newest': newest})
    if not r or r.status_code != 200:
        return None
    by_date = {}
    for d in r.json():
        k = (d.get('id') or d.get('date') or '')[:10]
        if d.get('ctl') is not None:
            by_date[k] = round(d['ctl'], 1)
    curve = []
    w = week1
    while w <= today:
        # find seneste kendte CTL på eller før denne uges mandag+6
        sun = w + timedelta(days=6)
        probe = min(sun, today)
        val = None
        for offset in range(7):
            candidate = str(probe - timedelta(days=offset))
            if candidate in by_date:
                val = by_date[candidate]
                break
        curve.append(val)
        w += timedelta(weeks=1)
    return curve
