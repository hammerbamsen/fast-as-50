"""AF-dage (alkoholfrie dage) — hentning og historik."""
from datetime import date, timedelta
from .config import BASE, AUTH, api_get, DAY_SHORT


def monday_this_week():
    """Returnerer mandag i indeværende uge."""
    from datetime import date, timedelta
    today = date.today()
    return today - timedelta(days=today.weekday())



def get_af_this_week():
    """AF-dage fra mandag denne uge.
    Returnerer (count, af_log) hvor af_log = {dato: True/False/None}
    True = AF-dag (Alkohol=0), False = ikke AF (Alkohol>0), None = ikke registreret
    """
    monday = monday_this_week()
    today  = date.today()
    r = api_get(f'{BASE}/wellness', auth=AUTH,
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
    r = api_get(f"{BASE}/wellness", auth=AUTH,
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
    r = api_get(f"{BASE}/wellness", auth=AUTH,
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
    r = api_get(f'{BASE}/wellness', auth=AUTH,
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
    # Tillad op til 2 uregistrerede dage i halen (i dag + i gaar
    # kan mangle check-in, da registrering ofte sker naeste aften)
    grace = 2
    while grace > 0 and str(check) not in af_by_date:
        check -= timedelta(days=1)
        grace -= 1
    while True:
        k = str(check)
        if af_by_date.get(k) == 0:
            streak += 1
            check -= timedelta(days=1)
        else:
            break
    print(f"  AF streak: {streak}")
    return streak
