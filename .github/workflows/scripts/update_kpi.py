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

# Disc-typer der er "planlagt træning" — bruges til at matche aktiviteter mod program
PLANNED_DISCS = {'run', 'bike', 'swim', 'openwater', 'strength'}
# Disc-typer der altid er "ekstra" og aldrig matcher planlagte sessioner
EXTRA_DISCS = {'walk', 'hike', 'commute', 'free'}

def parse_planned_mins(label):
    """Udtrækker planlagt varighed i minutter fra session-label. Fx '90 min' → 90."""
    m = re.search(r'(\d+)\s*min', label or '', re.IGNORECASE)
    return int(m.group(1)) if m else None

def completion_status(actual_tss, planned_tss, actual_mins, planned_mins, threshold=0.80):
    """
    Returnerer (status, pct) hvor status er:
      'done'    — ≥80% af planlagt TSS (eller tid hvis ingen TSS)
      'partial' — 20–79% gennemført
      'minimal' — <20% (dvs. nærmest ikke sket, fx 5 min løb)
    Bruger TSS som primær metrik, tid som fallback.
    """
    # Primær: TSS
    if planned_tss and planned_tss > 0 and actual_tss and actual_tss > 0:
        pct = actual_tss / planned_tss
        if pct >= threshold:
            return 'done', round(pct * 100)
        elif pct >= 0.20:
            return 'partial', round(pct * 100)
        else:
            return 'minimal', round(pct * 100)
    # Fallback: tid
    if planned_mins and planned_mins > 0 and actual_mins and actual_mins > 0:
        pct = actual_mins / planned_mins
        if pct >= threshold:
            return 'done', round(pct * 100)
        elif pct >= 0.20:
            return 'partial', round(pct * 100)
        else:
            return 'minimal', round(pct * 100)
    # Ingen data til at vurdere — antag done hvis matchet
    return 'done', None

def get_week_sessions_merged(planned_sessions):
    """
    Hent faktiske aktiviteter denne uge fra Intervals.icu.
    Merger med planlagte sessioner:
    - Planlagte sessioner markeres 'done' hvis der er en matchende aktivitet (disc+dag)
    - Ekstra aktiviteter (walk, hike, commute, free) tilføjes som bonus-rækker
    - Ikke-planlagte træningsaktiviteter (run/bike/swim uden planlagt match) tilføjes også
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
        return planned_sessions

    activities = r.json()
    if not activities:
        return planned_sessions

    # Byg aktiviteter grupperet pr. dag+disc
    actual_by_day = {}  # dag -> liste af aktiviteter
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

        if day_label not in actual_by_day:
            actual_by_day[day_label] = []
        actual_by_day[day_label].append({
            'disc':     disc,
            'label':    name,
            'dur':      dur_str,
            'dur_mins': dur_min,   # raw int til completion-beregning
            'tss':      tss,
        })

    # Start med kopi af planlagte sessioner
    result = []
    # Track hvilke aktiviteter der er brugt til at matche planlagte sessioner
    used = {day: [] for day in actual_by_day}

    for session in planned_sessions:
        day = session.get('day')
        disc = session.get('disc')
        new_session = dict(session)

        if day in actual_by_day:
            # Find første ubrugte aktivitet på denne dag med samme disc
            match = None
            for i, act in enumerate(actual_by_day[day]):
                if i not in used[day] and act['disc'] == disc:
                    match = act
                    used[day].append(i)
                    break

            if match:
                # Planlagt TSS: hentes fra session hvis sat, ellers estimér fra label
                planned_tss_val = session.get('planned_tss') or None
                planned_mins_val = parse_planned_mins(session.get('label', ''))
                actual_tss_val  = match['tss'] or 0
                actual_mins_val = match.get('dur_mins') or 0

                status, pct = completion_status(
                    actual_tss_val, planned_tss_val,
                    actual_mins_val, planned_mins_val
                )
                new_session['completion']     = status   # 'done'/'partial'/'minimal'
                new_session['completion_pct'] = pct      # fx 87 (%)
                new_session['actual_tss']     = actual_tss_val
                new_session['actual_mins']    = actual_mins_val
                new_session['planned_mins']   = planned_mins_val
                new_session['done'] = (status == 'done')
                if match['dur']:
                    new_session['dur'] = match['dur']
                if match['tss']:
                    new_session['tss'] = match['tss']

        result.append(new_session)

    # Tilføj ekstra aktiviteter der ikke matchede planlagte sessioner
    day_order = {d: i for i, d in enumerate(DK_DAYS)}
    extra_sessions = []
    for day, acts in actual_by_day.items():
        for i, act in enumerate(acts):
            if i not in used.get(day, []):
                extra_sessions.append({
                    'day':   day,
                    'disc':  act['disc'],
                    'label': act['label'],
                    'done':  True,
                    'dur':   act['dur'],
                    'tss':   act['tss'],
                    'extra': True,  # markér som bonus-aktivitet
                })

    # Indsæt ekstra aktiviteter på rigtig dag-position
    if extra_sessions:
        extra_sessions.sort(key=lambda s: day_order.get(s['day'], 9))
        # Merge: indsæt ekstra efter den planlagte session på samme dag
        merged = []
        for session in result:
            merged.append(session)
            day = session.get('day')
            day_extras = [e for e in extra_sessions if e['day'] == day]
            for extra in day_extras:
                merged.append(extra)
                extra_sessions.remove(extra)
        # Resterende ekstra (dage uden planlagt session)
        merged.extend(extra_sessions)
        result = merged

    return result

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

def generate_coach_voice(meta, ctl, tsb, af_streak, week_af_count,
                         weight, weight_is_today, sleep, run_km, tss_comp,
                         week_sessions=None):
    """
    Genererer coach-tekst med:
    - Korrekt fortid/fremtid baseret på session 'done'-status
    - Vægt kun nævnt hvis målt i dag
    - AF-kommentar tager højde for ugedag (ingen panik mandag)
    - Eksplicit holdning/vurdering, ikke bare faktalister
    """
    from datetime import date
    week      = meta['week']
    day_name  = meta['dayName']
    weekday   = date.today().weekday()  # 0=Man, 6=Søn
    cb_days   = meta.get('daysToChristiansborg', 75)
    cb_weeks  = cb_days // 7

    expected_ctl = 34 + (week - 1) * 1.9  # rute mod CTL 60 i uge 11

    # ── Sessioner: hvad er gjort, hvad mangler ─────────────────────
    done_sessions    = [s for s in (week_sessions or []) if s.get('done') and not s.get('extra')]
    pending_sessions = [s for s in (week_sessions or []) if not s.get('done') and not s.get('extra')]

    done_labels    = [s.get('label','') for s in done_sessions]
    pending_labels = [s.get('label','') for s in pending_sessions]

    # ── Vurderinger ───────────────────────────────────────────────
    verdicts = []   # holdning/vurdering — det vigtigste
    goods    = []   # positivt
    focus    = []   # kræver handling

    # Træning — Friel
    if ctl is not None:
        if ctl >= expected_ctl - 1:
            goods.append(f"CTL {ctl} følger ramp-kurven mod 60")
        else:
            focus.append(f"CTL {ctl} er lidt under kurven — byg gradvist op")

    if tsb is not None:
        if tsb < -30:
            verdicts.append(f"TSB {tsb} er under Friels -30-grænse — kroppen er i underskud. Restitution er nu højere prioritet end volumen.")
        elif tsb < -20:
            verdicts.append(f"TSB {tsb} — hård belastningsuge. Hold øje med træthed og prioriter søvn.")
        elif tsb < -10:
            goods.append(f"TSB {tsb} — sund belastning med plads til næste session")
        else:
            goods.append(f"TSB {tsb} — god form, klar til kvalitetstræning")

    # Sessioner — fortid/fremtid
    if done_labels:
        verdicts.append(f"Gennemført i dag: {done_labels[-1]}.")
    if pending_labels:
        next_s = pending_labels[0]
        verdicts.append(f"Næste op: {next_s}.")

    # Krop — Kreutzer (kun hvis vægt er målt i dag)
    if weight is not None and weight_is_today:
        if weight <= 72:
            goods.append(f"Vægt {weight} kg — i mål")
        elif weight <= 73.5:
            focus.append(f"Vægt {weight} kg — tæt på. Hold protein højt, lette kulhydrater ned om aftenen")
        else:
            focus.append(f"Vægt {weight} kg — Martin: protein prioritet, underskud om aftenen")

    if sleep is not None:
        if sleep >= 7.5:
            goods.append(f"Søvn {sleep}t — over målet")
        elif sleep >= 7:
            goods.append(f"Søvn {sleep}t er solid")
        else:
            focus.append(f"Søvn {sleep}t — under 7t-målet, prioriter det")

    # AF — tager højde for ugedag
    if week_af_count is not None:
        remaining_days = 6 - weekday  # dage tilbage i ugen inkl. i dag
        af_needed      = max(0, 5 - week_af_count)
        if week_af_count >= 5:
            goods.append(f"{week_af_count}/5 AF-dage i hus — streak {af_streak} dage")
        elif weekday == 0:
            # Mandag: ingen grund til bekymring endnu
            goods.append(f"AF-streak {af_streak} dage — uge 3 begyndt")
        elif af_needed > remaining_days:
            verdicts.append(f"Kun {week_af_count}/5 AF-dage og {remaining_days} dage tilbage — mål er matematisk svært. Sæt de næste dage i kalenderen nu.")
        else:
            focus.append(f"{week_af_count}/5 AF-dage — {af_needed} mangler, {remaining_days} dage tilbage")

    # ── Byg speech-tekst ──────────────────────────────────────────
    highlight = goods[0] if goods else f"CTL {ctl} — {cb_weeks} uger til Christiansborg"

    parts = []
    # Verdicts først (holdning)
    if verdicts:
        parts.append(" ".join(verdicts))
    # Focus (handlinger)
    if focus:
        parts.append("Fokus: " + " · ".join(focus[:2]) + ".")
    # Goods (positiv afslutning)
    if goods and not verdicts:
        parts.append(goods[0] + ".")

    if not parts:
        parts.append("Alt kører efter planen — hold rytmen.")

    speech = f"{day_name}, uge {week} af 14. {{HL}} " + " ".join(parts)
    return speech, highlight


def main():
    print("Henter data fra Intervals.icu...")


    fitness    = get_fitness()
    wellness   = get_wellness_7d()
    activities = get_activities_7d()
    planned    = planned_tss_this_week()
    af_streak, af_log, week_af_count = get_af_streak_and_log()
    meta       = week_meta()

    weight  = wellness.get('weight')   if wellness else None
    # weight_is_today: True kun hvis Intervals har en måling dateret i dag
    def _weight_today(raw_data):
        from datetime import date as _date
        today_str = str(_date.today())
        for d in (raw_data or []):
            if d.get('id','')[:10] == today_str and d.get('weight'):
                return True
        return False
    _raw_wellness = None
    try:
        _r = requests.get(f'{BASE}/wellness', auth=AUTH,
                          params={'oldest': str(date.today()), 'newest': str(date.today())})
        if _r.status_code == 200:
            _raw_wellness = _r.json()
    except Exception:
        pass
    weight_is_today = _weight_today(_raw_wellness)
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

    # Merge planlagte sessioner med faktiske Intervals-aktiviteter
    import os as _os
    current_sessions = existing.get('week_sessions', [])
    merged_sessions = get_week_sessions_merged(current_sessions)
    existing['week_sessions'] = merged_sessions
    _dbg2 = {
        'cwd': _os.getcwd(),
        'data_json_exists': _os.path.exists('data.json'),
        'current_count': len(current_sessions),
        'merged_count': len(merged_sessions),
        'merged': merged_sessions,
    }
    with open('debug_merge.json','w') as _f:
        json.dump(_dbg2, _f, ensure_ascii=False, indent=2)
    print(f"week_sessions: {len(merged_sessions)} sessioner (planlagte + ekstra)")

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

    coach_speech, coach_highlight = generate_coach_voice(
        meta, ctl, tsb, af_streak, week_af_count,
        weight, weight_is_today, sleep, run_km, tss_comp,
        week_sessions=merged_sessions
    )
    existing['coachSpeech'] = coach_speech
    existing['coachHighlight'] = coach_highlight


    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"Done! AF streak={af_streak}, uge={week_af_count}/5, CTL={ctl}, vægt={weight}")

if __name__ == '__main__':
    main()
