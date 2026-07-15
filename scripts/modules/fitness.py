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


def get_history_7d(existing=None):
    """Inkrementel historik: tilføj dagens wellness til eksisterende cache."""
    from datetime import date, timedelta
    DAYS = 90
    today_str = str(date.today())

    # Brug 7-dages kald - præcist samme som get_wellness_7d der virker
    oldest = str(date.today() - timedelta(days=7))
    newest = str(date.today())
    r = api_get(f'{BASE}/wellness', auth=AUTH, params={'oldest': oldest, 'newest': newest})

    daily = {}  # dato -> {weight, hrv, sleep, fat, tsb}
    if r and r.status_code == 200:
        rows = r.json()
        print(f"  history_7d: {len(rows)} rækker fra API")
        if rows:
            print(f"  history_7d sample keys: {list(rows[-1].keys())[:20]}")
        for row in rows:
            # Intervals bruger 'id' felt som dato (YYYY-MM-DD), ikke 'date'
            d = (row.get('id') or row.get('date') or '')[:10]
            if not d:
                continue
            ctl = row.get('ctl')
            atl = row.get('atl')
            tsb = row.get('tsb')
            tsb_val = round(ctl - atl, 1) if (ctl and atl) else (round(tsb, 1) if tsb else None)
            s = row.get('sleepSecs')
            daily[d] = {
                'weight': round(row['weight'], 1) if row.get('weight') is not None else None,
                'fat':    round(row['bodyFat'], 1) if row.get('bodyFat') is not None else None,
                'hrv':    round(row['hrv'], 1) if row.get('hrv') is not None else None,
                'sleep':  round(s / 3600, 1) if s else None,
                'tsb':    tsb_val,
            }
        print(f"  history_7d: {len(daily)} dage med dato")
    else:
        print(f"  history_7d: API fejl")

    dates = [str(date.today() - timedelta(days=i)) for i in range(DAYS - 1, -1, -1)]
    date_to_idx = {d: i for i, d in enumerate(dates)}

    def build(field, cache_key):
        cache = list((existing or {}).get(cache_key, []))
        if len(cache) < DAYS:
            cache = [None] * (DAYS - len(cache)) + cache
        elif len(cache) > DAYS:
            cache = cache[-DAYS:]
        # Normalisér eksisterende flade tal → dict (real=False: ukendt oprindelse)
        for i in range(DAYS):
            if cache[i] is not None and not isinstance(cache[i], dict):
                cache[i] = {'date': dates[i], 'v': cache[i], 'real': False}
        # Overskriv/tilføj dagens faktiske Intervals-målinger (real=True)
        for d_str, vals in daily.items():
            if d_str in date_to_idx and vals.get(field) is not None:
                cache[date_to_idx[d_str]] = {'date': d_str, 'v': vals[field], 'real': True}
        return cache

    return {
        'weightHistory': build('weight', 'weightHistory'),
        'fatHistory':    build('fat',    'fatHistory'),
        'hrvHistory':    build('hrv',    'hrvHistory'),
        'sleepHistory':  build('sleep',  'sleepHistory'),
        'tsbHistory':    build('tsb',    'tsbHistory'),
    }


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
