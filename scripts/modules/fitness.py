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
        hrvs    = [d.get('hrv')       for d in data if d.get('hrv')]
        sleeps  = [d.get('sleepSecs') for d in data if d.get('sleepSecs')]
        weights = [d.get('weight')    for d in data if d.get('weight')]
        fats    = [d.get('bodyFat')   for d in data if d.get('bodyFat')]
        proteins= [d.get('Protein')   for d in data if d.get('Protein')]
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
    """Bygger historik-lister dag for dag ved at tilføje dagens wellness til eksisterende cache."""
    from datetime import date, timedelta
    DAYS = 90
    today_str = str(date.today())

    # Hent dagens og seneste uges wellness (virker stabilt)
    oldest = str(date.today() - timedelta(days=7))
    newest = str(date.today())
    r = api_get(f'{BASE}/wellness', auth=AUTH, params={'oldest': oldest, 'newest': newest})
    
    raw = {}
    if r and r.status_code == 200:
        raw = {d['date'][:10]: d for d in r.json() if d.get('date')}
        print(f"  History wellness: {len(raw)} dage fra API")
    else:
        print(f"  History wellness: API fejl")

    def w_weight(row): return round(row['weight'], 1) if row.get('weight') is not None else None
    def w_fat(row):    return round(row['bodyFat'], 1) if row.get('bodyFat') is not None else None
    def w_hrv(row):    return round(row['hrv'], 1) if row.get('hrv') is not None else None
    def w_sleep(row):
        s = row.get('sleepSecs')
        return round(s / 3600, 1) if s else None
    def w_tsb(row):
        if row.get('ctl') is not None and row.get('atl') is not None:
            return round(row['ctl'] - row['atl'], 1)
        return round(row['tsb'], 1) if row.get('tsb') is not None else None

    def build(fn, cache_key):
        # Start med eksisterende cache (90 punkter)
        cache = list((existing or {}).get(cache_key, []))
        if len(cache) < DAYS:
            cache = [None] * (DAYS - len(cache)) + cache
        elif len(cache) > DAYS:
            cache = cache[-DAYS:]
        
        # Opbyg dato-index: hvilken index svarer til hvilken dato
        dates = [str(date.today() - timedelta(days=i)) for i in range(DAYS - 1, -1, -1)]
        date_to_idx = {d: i for i, d in enumerate(dates)}
        
        # Overskriv med API-data for de dage vi har
        updated = 0
        for d_str, row in raw.items():
            if d_str in date_to_idx:
                v = fn(row)
                if v is not None:
                    cache[date_to_idx[d_str]] = v
                    updated += 1
        
        if updated:
            print(f"    {cache_key}: {updated} dage opdateret fra API")
        return cache

    return {
        'weightHistory': build(w_weight, 'weightHistory'),
        'fatHistory':    build(w_fat,    'fatHistory'),
        'hrvHistory':    build(w_hrv,    'hrvHistory'),
        'sleepHistory':  build(w_sleep,  'sleepHistory'),
        'tsbHistory':    build(w_tsb,    'tsbHistory'),
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
        k = d.get('date', '')[:10]
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
