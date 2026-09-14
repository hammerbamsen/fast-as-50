"""AF-dage (alkoholfrie dage) — hentning og historik."""
from datetime import date, timedelta
from .config import BASE, AUTH, api_get, DAY_SHORT, PLAN_START, TOTAL_WEEKS, PROJECT_START


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


AF_HISTORY_WEEKS = 12


def get_af_history(weeks=AF_HISTORY_WEEKS):
    """AF-historik uge for uge, de seneste `weeks` uger (inkl. indeværende).
    14/9-2026: gik før kun tilbage til det aktive programs uge 1 — ved
    programskift 7/9 forsvandt 12 ugers historik. Hver uge bærer nu `monday`
    (ISO-dato), som frontend bruger til dag-opslag i af_log; `week` er
    program-relativ (kan være <= 0) og bruges kun til filtrering af
    indeværende uge.
    Returnerer [{week, iso, monday, done, total, label}, ...] ældst først.
    """
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    first_monday = this_monday - timedelta(weeks=weeks - 1)
    first_monday = max(first_monday, PROJECT_START - timedelta(days=PROJECT_START.weekday()))

    r = api_get(f"{BASE}/wellness", auth=AUTH,
                params={"oldest": str(first_monday), "newest": str(today)})
    if r.status_code != 200:
        return []

    wellness_by_date = {(d.get("id") or d.get("date") or "")[:10]: d for d in r.json()}

    history = []
    week_start = first_monday
    while week_start <= today:
        week_end = week_start + timedelta(days=6)
        count = days_passed = 0
        current = week_start
        while current <= min(week_end, today):
            if wellness_by_date.get(str(current), {}).get("Alkohol") == 0:
                count += 1
            days_passed += 1
            current += timedelta(days=1)
        iso_week = week_start.isocalendar()[1]
        history.append({
            "week": (week_start - PLAN_START).days // 7 + 1,
            "iso": iso_week,
            "monday": str(week_start),
            "done": count,
            "total": days_passed,
            "label": f"Uge {iso_week}",
        })
        week_start += timedelta(days=7)

    print(f"  AF historik: {history}")
    return history


def get_full_af_log():
    """Henter dag-for-dag AF log siden projektstart (første program) til index.html's log-ark (af.html slettet blok 9).
    Returnerer {dato: 0/1} hvor 0 = AF-dag, 1 = ikke AF.
    """
    project_start = PROJECT_START
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

def detect_alcohol_cluster(full_af_log, window_days=7, min_run=2, today=None):
    """Finder længste sammenhængende række drikkedage inden for de seneste
    window_days.

    full_af_log: {dato-iso: 0/1} som fra get_full_af_log() — 0 = AF-dag,
    1 = drikkedag. Uregistrerede dage bryder rækken (de tælles ikke med).

    Returnerer dict {'days': n, 'start': iso, 'end': iso} for den længste
    række på mindst min_run dage, ellers None.
    """
    if not full_af_log:
        return None
    if today is None:
        today = date.today()

    best = None
    run_len = 0
    run_end = None

    for offset in range(window_days):
        day = today - timedelta(days=offset)
        if full_af_log.get(str(day)) == 1:
            if run_len == 0:
                run_end = day
            run_len += 1
            if run_len >= min_run and (best is None or run_len > best['days']):
                best = {
                    'days':  run_len,
                    'start': str(day),
                    'end':   str(run_end),
                }
        else:
            run_len = 0
            run_end = None

    return best


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
