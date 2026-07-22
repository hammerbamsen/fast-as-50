#!/usr/bin/env python3
"""
Fast as Fifty — KPI dashboard opdatering.
Henter data fra Intervals.icu og skriver data.json til GitHub Pages.
Køres via GitHub Actions (hvert 10. min dag / 30. min nat).

Modulstruktur:
  scripts/modules/config.py   — konstanter, api_get, fmt, color_for
  scripts/modules/fitness.py  — CTL/ATL/TSB/HRV/wellness
  scripts/modules/af.py       — alkoholfrie dage
  scripts/modules/sessions.py — aktiviteter, planlagte workouts, compliance
  scripts/modules/coach.py    — coach-tekst og AI-assessment
  scripts/modules/github.py   — læs/skriv data.json via GitHub API
"""
import os, re, json, base64, sys, subprocess
from datetime import date, datetime, timedelta

# Sørg for at 'modules/' kan findes uanset hvorfra scriptet køres
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Moduler ──────────────────────────────────────────────────────────────────
from modules.config   import (API_KEY, ATHLETE_ID, GH_TOKEN, ANTHROPIC_KEY,
                               REPO, BASE, AUTH, CTL_PLAN, BLOCK_TYPES,
                               PLAN_START, TOTAL_WEEKS, RACES,
                               DK_DAYS, DAY_SHORT, DK_MONTHS,
                               CTL_START, CTL_GOAL, AF_GOAL, SLEEP_GOAL_HOURS,
                               SWIM_GOAL_M, RUN_KM_GOAL, RUN_KM_GOAL_WEEK,
                               api_get, ctl_plan_for_week, fix_enc, fmt, color_for)
from modules.fitness  import get_fitness, get_wellness_7d, get_history, get_ctl_curve
from modules.af       import (get_af_this_week, get_af_history, get_full_af_log,
                               get_af_streak, monday_this_week)
from modules.sessions import (get_activities_week, get_workout_compliance_this_week,
                               format_compliance_for_prompt, get_planned_mins_this_week,
                               planned_tss_this_week, parse_planned_mins, calc_completion,
                               build_week_sessions, get_planned_weeks, generate_week_focus,
                               generate_week_focus_ai, get_swim_history)
import modules.coach as _coach_mod
from modules.coach    import (get_travel_label, weight_delta_vs_recent,
                               build_weight_context_note, build_trajectory_note,
                               qa_coach_speech, generate_coach_speech, generate_ai_assessment)
from modules.github   import gh_get, gh_put


def _sync_repo():
    """Pull frisk kode fra origin/main før run — sikrer Mac launchd altid bruger
    seneste version. Skip'es i GitHub Actions hvor checkout allerede er frisk.
    Fejler blødt: script fortsætter selv hvis pull ikke lykkes."""
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isdir(os.path.join(repo_root, '.git')):
        return  # ikke et git-repo (fx sandbox-kørsel)
    try:
        r = subprocess.run(
            ['git', '-C', repo_root, 'pull', '--rebase', '--autostash', '--quiet'],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            print("  ✅ Git sync: up-to-date")
        else:
            print(f"  ⚠️ Git sync fejlede (fortsætter): {(r.stderr or r.stdout)[:150]}")
    except Exception as e:
        print(f"  ⚠️ Git sync exception (fortsætter): {e}")


def main():
    _sync_repo()
    today     = date.today()
    weekday   = today.weekday()
    week1     = PLAN_START
    week_num  = min(max((today - week1).days // 7 + 1, 1), TOTAL_WEEKS)

    print(f"=== KPI opdatering {today} (uge {week_num}) ===")

    fitness    = get_fitness()
    wellness   = get_wellness_7d()
    activities   = get_activities_week()
    planned_weeks = get_planned_weeks()
    planned    = planned_tss_this_week()

    # Hent planlagte events og beregn zone-compliance
    _monday_ce = date.today() - timedelta(days=date.today().weekday())
    _r_events_ce = api_get(f'{BASE}/events', auth=AUTH,
                                 params={'oldest': str(_monday_ce), 'newest': str(date.today())})
    _events_this_week = _r_events_ce.json() if _r_events_ce and _r_events_ce.status_code == 200 else []
    _r_acts_ce = api_get(f'{BASE}/activities', auth=AUTH,
                               params={'oldest': str(_monday_ce), 'newest': str(date.today())})
    _acts_this_week = _r_acts_ce.json() if _r_acts_ce and _r_acts_ce.status_code == 200 else []
    workout_compliance = get_workout_compliance_this_week(_events_this_week, _acts_this_week)
    compliance_summary = format_compliance_for_prompt(workout_compliance)
    if compliance_summary:
        print(f"  Compliance summary:\n{compliance_summary}")

    af_days, af_log = get_af_this_week()
    af_streak = get_af_streak()
    # Dage anses for "afsluttede" når de har en registreret AF-værdi i af_log
    # (inkl. i dag, hvis Alkohol allerede er logget) -- IKKE blot kalenderens
    # ugedag. Forhindrer mismatch som "7 AF-dage ud af 6 afsluttede dage".
    days_completed = weekday + 1  # Alle kalenderdage fra mandag t.o.m. i dag (0=man, 4=fre)
    try:
        history    = get_history()  # fuldt 90-dages vindue, bygget efter dato
    except Exception as _e:
        print(f"  HISTORY FEJL: {_e}")
        import traceback; traceback.print_exc()
        history = None
    ctl_curve  = get_ctl_curve()
    swim_history = get_swim_history()
    print(f"  Svøm historik: {len(swim_history)} uger")

    print(f"  Fitness:    {fitness}")
    print(f"  Wellness:   {wellness}")
    print(f"  Aktivitet:  {activities}")
    print(f"  AF-dage:    {af_days}")
    print(f"  Planlagt:   {planned} TSS")

    # --- Hent data.json ---
    sha_data, data_raw = gh_get('data.json')
    if not data_raw:
        print("❌ Kunne ikke hente data.json — afbryder med exit 1 så Actions-kørslen bliver RØD")
        sys.exit(1)
    data = json.loads(data_raw)
    data.pop('_debug_activities_tss', None)  # ryd op efter tidligere TSS-diagnose
    data.pop('_debug_full_activity', None)   # ryd op efter denne kørsel (sat igen nedenfor om nødvendigt)

    # --- Opdater meta ---
    try:
        from zoneinfo import ZoneInfo
        now_cph = datetime.now(ZoneInfo("Europe/Copenhagen"))
    except Exception:
        # Fallback hvis tzdata mangler på runner: UTC+2 (DK sommertid)
        now_cph = datetime.utcnow() + timedelta(hours=2)
    data['meta']['updated']              = now_cph.strftime("%Y-%m-%d %H:%M")
    data['meta']['dayName']              = DK_DAYS[weekday]
    data['meta']['date']                 = f"{today.day}. {DK_MONTHS[today.month-1]}"
    _race_dates = {r['name']: date.fromisoformat(r['date']) for r in RACES}
    data['meta']['daysToMedoc']          = ((_race_dates.get('Marathon du Médoc') or date(2026, 9, 5)) - today).days
    data['meta']['daysToChristiansborg'] = ((_race_dates.get('Christiansborg Rundt') or date(2026, 8, 29)) - today).days
    data['meta']['week']                 = week_num
    data['meta']['totalWeeks']           = TOTAL_WEEKS
    data['ctlPlan']                      = CTL_PLAN

    # --- Mål (sættes FØR KPI-blokken bygges, da den læser disse felter) ---
    data['weightGoal']   = 70
    data['bodyFatGoal']  = 20

    # --- KPIs ---
    weight     = wellness.get('weight')   if wellness else None

    # weight_is_today: kun True hvis Intervals har en REEL måling dateret præcis i dag
    def _weight_today(rows):
        today_str = str(date.today())
        for row in (rows or []):
            dt = (row.get('id') or row.get('date') or '')[:10]
            if dt == today_str and row.get('weight') is not None:
                return True
        return False
    _r_today = api_get(f'{BASE}/wellness', auth=AUTH,
                            params={'oldest': str(date.today()), 'newest': str(date.today())})
    _today_rows = _r_today.json() if _r_today.status_code == 200 else []
    weight_is_today = _weight_today(_today_rows)

    # --- Rejse-/vægtudsving-kontekst: undgå at coachen bebrejder disciplin når
    # et udsving skyldes rejse (fx hjemkomst fra Mallorca) fremfor fedt — og,
    # lige så vigtigt, undgå at påstå retention hvis vægten faktisk er FALDET ---
    travel_label = get_travel_label(str(today))
    w_delta, w_prior_date = weight_delta_vs_recent(
        (history or {}).get('weightHistory', []), str(today),
        weight if weight_is_today else None
    )
    context_note = build_weight_context_note(travel_label, w_delta, w_prior_date)
    if context_note:
        print(f"  Kontekst-note (vægt): {context_note}")

    weight_avg = wellness.get('weight_avg') if wellness else None
    fat        = wellness.get('fat')        if wellness else None
    protein    = wellness.get('protein')    if wellness else None
    hrv    = wellness.get('hrv_avg') if wellness else None
    sleep  = wellness.get('sleep_avg') if wellness else None
    ctl    = fitness.get('ctl')      if fitness else None
    atl    = fitness.get('atl')      if fitness else None
    tsb    = fitness.get('tsb')      if fitness else None
    tss_act = activities.get('tss_week') if activities else None
    km_week  = activities.get('run_km')  if activities else None
    swim_m   = activities.get('swim_m')   if activities else None
    bike_km  = activities.get('bike_km') if activities else None
    done_map   = activities.get('done_map', {})    if activities else {}
    train_mins = activities.get('train_mins', {}) if activities else {}
    compliance = round(tss_act / planned * 100, 0) if tss_act else None

    # --- Ugentligt 'store billede' — kun søndage (weekday 6), så det ikke
    # drukner den daglige tekst resten af ugen. Viser CTL-pace mod den rigtige
    # ugeplan + vægtens udvikling over flere uger, ikke kun dagens snapshot. ---
    trajectory_note = None
    if weekday == 6:
        trajectory_note = build_trajectory_note(
            week_num, ctl,
            weight if weight_is_today else None,
            (history or {}).get('weightHistory', [])
        )
        if trajectory_note:
            print(f"  Store billede (søndag): {trajectory_note}")

    tss_color = color_for(compliance, 85, lower=False) if compliance else '#7A6A58'
    data['kpis'] = {
        'weight':     {'value': fmt(weight),          'unit': 'kg', 'sub': f"Mål <{data['weightGoal']} kg · snit {fmt(weight_avg)} kg" if weight_avg else f"Mål <{data['weightGoal']} kg", 'color': color_for(weight, data['weightGoal'], lower=True)  if weight     else '#7A6A58'},
        'fat':        {'value': fmt(fat),              'unit': '%',  'sub': f"Mål <{data['bodyFatGoal']}%",                       'color': color_for(fat, data['bodyFatGoal'], lower=True)     if fat        else '#7A6A58'},
        'ctl':        {'value': fmt(ctl, 1),           'unit': '',   'sub': f'Uge {week_num}-mål {ctl_plan_for_week(week_num)} · Slutmål {CTL_GOAL} (uge {len(CTL_PLAN)})', 'color': color_for(ctl, CTL_GOAL, lower=False)    if ctl        else '#7A6A58'},
        'tsb':        {'value': fmt(tsb, 1),           'unit': '',   'sub': ('Hård blok · CTL−ATL, frisk >0' if tsb and tsb < -10 else 'Form · CTL−ATL, frisk >0'), 'color': '#E67E22' if tsb and tsb < -10 else '#27AE60'},
        'sleep':      {'value': fmt(sleep, 1),         'unit': 't',  'sub': f'Snit 7,5t · mål {SLEEP_GOAL_HOURS}t',            'color': '#2874A6'},
        'runKm':      {'value': fmt(km_week, 1),       'unit': 'km', 'sub': f'Mål {RUN_KM_GOAL}+ km uge {RUN_KM_GOAL_WEEK}',             'color': color_for(km_week, 20, lower=False) if km_week   else '#7A6A58'},
        'hrv':        {'value': fmt(hrv, 1),           'unit': 'ms', 'sub': 'Snit 7d',                       'color': '#7A6A58'},
        'tssComp':    {'value': fmt(tss_act, 0) if tss_act else '0', 'unit': 'TSS',
                       'sub': f'{int(tss_act or 0)} af {int(planned)} planlagt TSS',
                       'color': tss_color},
        'bikeKm':     {'value': fmt(bike_km, 1),       'unit': 'km', 'sub': 'Cykel denne uge',                  'color': color_for(bike_km, 50, lower=False) if bike_km else '#7A6A58'},
        'swimM':      {'value': fmt(swim_m, 0) if swim_m else '0',    'unit': 'm',  'sub': f'Svøm denne uge · mål {SWIM_GOAL_M}m (Christiansborg)',  'color': color_for(swim_m, SWIM_GOAL_M, lower=False) if swim_m else '#7A6A58'},
        'afStreak':   {'value': str(af_streak),        'unit': '',   'sub': f'Dage i træk · mål {AF_GOAL}/uge',           'color': '#59182A'},
    }

    # --- TSB / HRV advarsler (sendes til dashboard for visning) ---
    warnings = []
    if tsb is not None and tsb < -30:
        warnings.append({
            'type':    'tsb',
            'level':   'critical',
            'message': f'TSB {fmt(tsb,1)} — høj træthed. Overvej let dag eller hvile.',
        })
    elif tsb is not None and tsb < -20:
        warnings.append({
            'type':    'tsb',
            'level':   'warn',
            'message': f'TSB {fmt(tsb,1)} — hård belastning. Hold øje med trætheden.',
        })

    # HRV-advarsel: sammenlign dagens HRV med 7d-snit
    hrv_today = None
    if wellness:
        hrv_today = wellness.get('hrv')   # direkte dagens HRV (wellness_7d sætter altid hrv = seneste)
        hrv_avg7  = wellness.get('hrv_avg')
        if hrv_today and hrv_avg7 and hrv_avg7 > 0:
            hrv_drop_pct = (hrv_avg7 - hrv_today) / hrv_avg7 * 100
            if hrv_drop_pct > 10:
                warnings.append({
                    'type':    'hrv',
                    'level':   'warn',
                    'message': f'HRV {fmt(hrv_today,1)} ms — {round(hrv_drop_pct)}% under 7d-snit ({fmt(hrv_avg7,1)} ms). Kroppen er presset.',
                })

    data['warnings'] = warnings
    if warnings:
        print(f"  ⚠️  Advarsler: {[w['message'] for w in warnings]}")

    data['tsb'] = tsb  # direkte TSB-tal til brug i frontend advarsler
    # --- AF-dage (man–søn denne uge) ---
    data['af'] = {
        'weekDone': af_days if af_days is not None else data.get('af', {}).get('weekDone', 0),
        'target': 5,
        'streak': af_streak
    }

    # --- AF log: dag-for-dag til af.html sync (alle uger siden projektstart) ---
    full_af_log = get_full_af_log()
    if full_af_log:
        data["af_log"] = full_af_log
        print(f"  AF log (alle dage): {len(full_af_log)} dage")

    # --- AF historik: uge-for-uge siden projektstart ---
    af_history = get_af_history()
    if af_history:
        data['af_history'] = af_history

    # --- Træningstimer per type + planlagt ---
    planned_mins = get_planned_mins_this_week()
    # Altid overskriv train_mins — også ved ugestart hvor der ingen aktiviteter er endnu
    actual_total = sum(train_mins.values())
    data['train_mins'] = train_mins
    data['train_mins']['planned'] = planned_mins
    data['train_mins']['actual_total'] = round(actual_total, 0)

    # --- Week sessions med done fra Intervals ---
    # Brug friske sessions fra Intervals (med fix_enc) — ikke stale labels fra data.json
    this_week_planned = planned_weeks.get(week_num, {}).get('sessions', data.get('week_sessions', []))
    data['week_sessions'] = build_week_sessions(done_map, this_week_planned)

    # --- Historik-grafer live fra Intervals (sparklines + CTL-kurve) ---
    if history:
        if history.get('weightHistory'): data['weightHistory'] = history['weightHistory']
        if history.get('fatHistory'):    data['fatHistory']    = history['fatHistory']
        if history.get('hrvHistory'):    data['hrvHistory']    = history['hrvHistory']
        if history.get('sleepHistory'):  data['sleepHistory']  = history['sleepHistory']
        if history.get('tsbHistory'):    data['tsbHistory']    = history['tsbHistory']
        print(f"  Historik: vægt={len(history.get('weightHistory',[]))} hrv={len(history.get('hrvHistory',[]))} søvn={len(history.get('sleepHistory',[]))} tsb={len(history.get('tsbHistory',[]))} punkter")

    # --- Glidende 7-dages gennemsnit (vægt + fedt) ---
    def _moving_avg_7(series):
        def _v(x):
            return x.get('v') if isinstance(x, dict) else x
        result = []
        for i in range(len(series)):
            window_vals = [_v(x) for x in series[max(0, i-6):i+1] if x is not None and _v(x) is not None]
            result.append(round(sum(window_vals)/len(window_vals), 2) if len(window_vals) >= 3 else None)
        return result

    _wh = data.get('weightHistory', [])
    _fh = data.get('fatHistory', [])
    data['weightMovingAvg7'] = _moving_avg_7(_wh)
    data['fatMovingAvg7']    = _moving_avg_7(_fh)

    # --- Afstand til mål ---
    _latest_w = next((v['v'] if isinstance(v, dict) else v for v in reversed(_wh) if v is not None and (v.get('v') if isinstance(v, dict) else v) is not None), None)
    _latest_f = next((v['v'] if isinstance(v, dict) else v for v in reversed(_fh) if v is not None and (v.get('v') if isinstance(v, dict) else v) is not None), None)
    data['weightToGoal']   = round(_latest_w - data['weightGoal'], 2) if _latest_w else None
    data['bodyFatToGoal']  = round(_latest_f - data['bodyFatGoal'], 1) if _latest_f else None
    if ctl_curve:
        data['ctlCurve'] = ctl_curve
        print(f"  CTL-kurve: {len(ctl_curve)} ugepunkter, seneste {ctl_curve[-1]}")
    if swim_history:
        data['swimHistory'] = swim_history

    # --- all_weeks: forrige/denne/næste uge fra Intervals ---
    if planned_weeks:
        # Merge done_map ind i denne uges sessions
        this_week = planned_weeks.get(week_num, {})
        if this_week:
            this_week['sessions'] = build_week_sessions(done_map, this_week['sessions'])
            _focus_cached_week = data.get('weekFocusWeek')
            _focus_cached_text = data.get('weekFocus', '')
            if _focus_cached_week == week_num and _focus_cached_text:
                print(f"  weekFocus cached (uge {week_num}) -- springer AI-kald over")
                dynamic_focus = _focus_cached_text
            else:
                # Hent Master Plan-note for denne uge
                _master_notes = {
                    1: 'Etableringsuge — TSB endte -8',
                    2: 'Mallorca uge. TSS synkroniseringsfejl.',
                    3: 'Mallorca-camp gennemført.',
                    4: 'Recovery uge. Fuldt AF 7/7.',
                    5: 'Tilbage til hverdagsrytme.',
                    6: 'Rejseuge — let cykel/løb, vedligehold.',
                    7: 'Stor cykel-uge #2.',
                    8: 'Restitution + rejsedag hjem.',
                    9: 'Musik i Gentofte i ugen efter (31/7–2/8) – planlæg let.',
                    10: 'Svømme-fokus øges mod Christiansborg Rundt.',
                    11: 'Peak TSS-uge.',
                    12: 'Svømme-specifik uge, nedtrapning starter.',
                    13: f'Race week: {SWIM_GOAL_M} m svøm 29/8. Taper ind, kort løb.',
                    14: 'Marathon Médoc 5/9.',
                }
                _week_note = _master_notes.get(week_num)
                dynamic_focus = generate_week_focus_ai(
                    week_num, this_week.get('sessions', []),
                    BLOCK_TYPES.get(week_num, 'BUILD'),
                    ctl=ctl, tsb=tsb,
                    week_note=_week_note,
                    anthropic_key=ANTHROPIC_KEY
                )
                data['weekFocusWeek'] = week_num
            dynamic_focus = fix_enc(dynamic_focus)
            this_week['focus'] = dynamic_focus
            data['weekFocus'] = dynamic_focus
        # Sæt fokus-tekst for alle uger — aktuel uge er allerede sat ovenfor,
        # fremtidige og forrige uger bruger cached fokus fra eksisterende data.json
        # eller fallback til den hurtige regelbaserede generator (ikke AI).
        _existing_all_weeks = data.get('all_weeks', {})
        for w_num, w_data in planned_weeks.items():
            if w_num == week_num:
                continue  # Aktuel uge allerede håndteret
            _cached_focus = fix_enc(_existing_all_weeks.get(str(w_num), {}).get('focus', ''))
            if _cached_focus:
                w_data['focus'] = _cached_focus
            else:
                w_data['focus'] = fix_enc(generate_week_focus(
                    w_num, w_data.get('sessions', []),
                    BLOCK_TYPES.get(w_num, 'BUILD')
                ))
        data['all_weeks'] = {str(k): v for k, v in planned_weeks.items()}

    # --- Today session(s) ---
    # NB: der kan være flere sessioner samme dag (fx styrke + løb) — tag dem ALLE, ikke kun den første.
    today_sessions_all = [s for s in data['week_sessions'] if s.get('today')]
    today_session = today_sessions_all[0] if today_sessions_all else None  # bruges til coach-speech mv. (primær session)
    if today_sessions_all:
        data['today'] = [
            {
                'discipline': s.get('disc', 'free'),
                'title':      s.get('label', ''),
                'duration':   s.get('duration', ''),
                'zone':       s.get('zone', '–'),
                'desc':       s.get('desc', ''),
                'completed':  s.get('done', False),
            }
            for s in today_sessions_all
        ]
    else:
        # Ingen session i dag = hviledag. Sæt eksplicit — ellers bliver
        # gårsdagens 'today' hængende (bug: appen viste et forkert pas).
        data['today'] = [
            {
                'discipline': 'rest',
                'title':      'Hviledag',
                'duration':   '',
                'zone':       '–',
                'desc':       'Ingen planlagt træning i dag.',
                'completed':  False,
            }
        ]

    # --- Coach speech (genereres dagligt) ---
    block_type = data.get('blockType', 'BUILD')
    week_focus = fix_enc(data.get('weekFocus', ''))
    data['weekFocus'] = week_focus  # Gem den rettede version tilbage
    af_this_week = data.get('af', {}).get('weekDone', 0)
    # remaining_sessions beregnes nu inde i generate_coach_speech fra week_sessions
    # -- send ikke stale liste her
    coach_speech, coach_highlight = generate_coach_speech(
        week_num, weekday, af_streak, af_this_week, today_session, block_type, week_focus,
        ctl=ctl, tsb=tsb, weight=weight if weight_is_today else None, sleep=sleep, compliance=compliance,
        tss_act=tss_act, planned=planned, week_sessions=data['week_sessions'],
        travel_note=context_note, trajectory_note=trajectory_note, days_completed=days_completed,
        weight_goal=data['weightGoal']
    )

    # --- QA: valider coach-tekst mod faktiske data inden push ---
    qa_errors = qa_coach_speech(
        coach_speech, data['week_sessions'],
        ctl=ctl, tsb=tsb, weight=weight,
        af_this_week=af_this_week, tss_act=tss_act, planned=planned,
        weight_goal=data['weightGoal']
    )
    if qa_errors:
        # Behold forrige gyldige tekst -- skriv fejl til log men push ikke forkert tekst
        print(f"  Coach QA fejlede -- beholder forrige coachSpeech")
        existing_speech = data.get('coachSpeech', '')
        if existing_speech:
            coach_speech = existing_speech
            coach_highlight = data.get('coachHighlight', coach_highlight)

    data['coachSpeech']    = coach_speech
    data['coachHighlight'] = coach_highlight

    # --- AI coach-vurdering (genereres server-side, caches i data.json, maks 1x/6t,
    #     MEN brydes tidligt hvis der kommer en ny vejning der afviger fra cachen) ---
    CACHE_HOURS = 6
    _cache_age_h = None
    _last_ts_full = data.get('coachAssessmentTsFull')
    if _last_ts_full:
        try:
            _last_dt = datetime.fromisoformat(_last_ts_full)
            _cache_age_h = (datetime.utcnow() - _last_dt).total_seconds() / 3600
        except Exception:
            _cache_age_h = None

    _weight_at_gen = data.get('coachAssessmentWeightAtGen')
    _weight_changed = (
        weight is not None
        and (_weight_at_gen is None or abs(weight - _weight_at_gen) > 0.05)
    )

    _af_at_gen = data.get('coachAssessmentAfAtGen')
    _af_changed = (_af_at_gen is None or af_this_week != _af_at_gen)

    # Ny aktivitet siden sidst cache blev genereret?
    _last_act_id_at_gen = data.get('coachAssessmentLastActId')
    _latest_act_id = (_acts_this_week[0].get('id') if _acts_this_week else None)
    _activity_changed = (
        _latest_act_id is not None
        and _latest_act_id != _last_act_id_at_gen
    )

    # Plan ændret siden cache? (bytte af sessioner, fx svøm <-> styrke)
    _today_label = (today_session.get('label', '') if today_session else '')
    _plan_at_gen = data.get('coachAssessmentPlanAtGen', '')
    _plan_changed = _today_label != _plan_at_gen

    if _cache_age_h is not None and _cache_age_h < CACHE_HOURS and not _weight_changed and not _af_changed and not _activity_changed and not _plan_changed:
        print(f"  Coach-vurdering cached ({_cache_age_h:.1f}t gammel) -- springer AI-kald over")
        ai_text = None
    else:
        if _weight_changed:
            print(f"  Ny vejning ({_weight_at_gen} -> {weight}) -- bryder cache tidligt")
        if _af_changed:
            print(f"  AF-status ændret ({_af_at_gen} -> {af_this_week}) -- bryder cache tidligt")
        if _activity_changed:
            print(f"  Ny aktivitet ({_last_act_id_at_gen} -> {_latest_act_id}) -- bryder cache tidligt")
        ai_text = generate_ai_assessment(
            week_num, weekday, DK_DAYS[weekday],
            ctl, tsb,
            weight if weight_is_today else None,
            af_this_week, af_streak,
            data['week_sessions'], week_focus,
            today_session, tss_act, planned,
            travel_note=context_note, trajectory_note=trajectory_note, days_completed=days_completed,
            compliance_summary=compliance_summary,
            weight_goal=data['weightGoal']
        )
        ai_text = fix_enc(ai_text)  # AI-svar kan komme tilbage Latin-1-mis-decoded -- ret ved kilden
    if ai_text:
        # Konverter til simpel HTML (samme logik som dashboardet)
        # Tilføj korrekt header hardcodet (forhindrer AI i at skrive forkert "Dag X af 14 uger")
        program_day = (date.today() - PLAN_START).days + 1
        header_str = f"Dag {program_day} af 98 · {DK_DAYS[weekday]} · Uge {week_num}"
        header_html = f'<p style="margin:0 0 8px;font-family:\'Hanken Grotesk\',sans-serif;font-size:14px;line-height:1.6;color:var(--ink)"><strong>{header_str}</strong></p>'
        html_lines = [header_html]
        for line in ai_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            html_lines.append(f'<p style="margin:0 0 8px;font-family:\'Hanken Grotesk\',sans-serif;font-size:14px;line-height:1.6;color:var(--ink)">{line}</p>')
        from datetime import datetime as _dt
        data['coachAssessmentHtml']        = fix_enc(''.join(html_lines))
        data['coachAssessmentTs']          = _dt.now().strftime('%H:%M')
        data['coachAssessmentTsFull']      = datetime.utcnow().isoformat()
        data['coachAssessmentWeightAtGen'] = weight if weight is not None else _weight_at_gen
        data['coachAssessmentAfAtGen']     = af_this_week
        data['coachAssessmentLastActId']   = _latest_act_id
        data['coachAssessmentPlanAtGen']   = _today_label
        data['coachAssessmentError'] = None
    else:
        # Behold eksisterende (cache stadig frisk, eller API fejlede)
        if not data.get('coachAssessmentHtml'):
            data['coachAssessmentHtml'] = ''
            data['coachAssessmentTs']   = ''
        # Fejlede AI-kaldet (i modsætning til: cachen var bare frisk)? Gør det synligt.
        _ai_err = getattr(_coach_mod, 'LAST_AI_ERROR', None)
        data['coachAssessmentError'] = _ai_err
        if _ai_err:
            print(f"  ❌ Coach-vurdering IKKE opdateret: {_ai_err}")

    # Er den viste vurdering fra en tidligere dag? Dashboardet skal kunne råbe op.
    _shown_ts = data.get('coachAssessmentTsFull')
    _stale = False
    if _shown_ts:
        try:
            _stale = datetime.fromisoformat(_shown_ts).date() != date.today()
        except Exception:
            _stale = False
    data['coachAssessmentStale'] = _stale
    if _stale:
        print(f"  ❌ Coach-vurdering er STALE (genereret {_shown_ts}, i dag er {date.today()})")

    # --- Credential-healthcheck ------------------------------------------
    # De to nedbrud 14.-15. juli skyldtes begge nøgler der døde TAVST:
    # PRIVATE_REPO_TOKEN udløb, og ANTHROPIC_API_KEY blev overskrevet med
    # et SSH-fingerprint. Ingen af delene sagde fra — de blev opdaget ved at
    # noget andet så forkert ud et døgn senere. Her valideres nøglerne ved
    # HVER kørsel, så dashboardet kan advare FØR noget står stille.
    _cred = {}

    # Intervals: virkede kaldet der hentede dagens data?
    _cred['intervals'] = {
        'ok': ctl is not None,
        'note': 'Nøgle virker' if ctl is not None else 'Intervals-kald gav intet svar — tjek INTERVALS_API_KEY',
    }

    # Anthropic: formatcheck + resultatet af det faktiske kald i denne kørsel
    _ak = (ANTHROPIC_KEY or '').strip()
    if not _ak:
        _anth = {'ok': False, 'note': 'ANTHROPIC_API_KEY er tom'}
    elif not _ak.startswith('sk-ant-'):
        _anth = {'ok': False, 'note': 'ANTHROPIC_API_KEY har forkert format (skal starte med sk-ant-) — forkert værdi indsat?'}
    elif ANTHROPIC_KEY != _ak:
        _anth = {'ok': False, 'note': 'ANTHROPIC_API_KEY har mellemrum/linjeskift omkring sig — vil fejle på header'}
    elif data.get('coachAssessmentError'):
        _anth = {'ok': False, 'note': f"Seneste AI-kald fejlede: {data['coachAssessmentError']}"}
    else:
        _anth = {'ok': True, 'note': 'Nøgle virker'}
    _cred['anthropic'] = _anth

    data['credentials'] = _cred
    data['credentialsCheckedTs'] = datetime.utcnow().isoformat()
    _bad = [k for k, v in _cred.items() if not v['ok']]
    if _bad:
        print(f"  ❌ CREDENTIAL-PROBLEM: {', '.join(_bad)}")
        for k in _bad:
            print(f"     {k}: {_cred[k]['note']}")
    else:
        print("  ✅ Credentials OK: intervals, anthropic")

    # --- Check: er et workout-event fejlagtigt parret med en commute-aktivitet? ---
    try:
        _week_start = today - timedelta(days=today.weekday())  # Mandag denne uge
        _r_commute = api_get(f'{BASE}/events', auth=AUTH,
            params={'oldest': str(_week_start), 'newest': str(today)})
        _events_today = _r_commute.json() if _r_commute and _r_commute.status_code == 200 else []
        _commute_warnings = []
        for _ev in (_events_today if isinstance(_events_today, list) else []):
            if _ev.get('category') != 'WORKOUT':
                continue
            _paired_id = _ev.get('paired_activity_id')
            if not _paired_id:
                continue
            _act_r = api_get(f'{BASE}/activities/{_paired_id}', auth=AUTH)
            if not _act_r or _act_r.status_code != 200:
                continue
            _act_list = _act_r.json()
            _act = _act_list[0] if isinstance(_act_list, list) else _act_list
            if _act.get('commute'):
                _commute_warnings.append({
                    'event': _ev.get('name', '?'),
                    'activity': _act.get('name', '?'),
                    'activity_id': _paired_id,
                    'event_id': _ev.get('id'),
                })
                print(f"  ⚠️ Commute-parring: '{_ev.get('name')}' er parret med commute '{_act.get('name')}' ({_paired_id})")
        data['commute_pairing_warnings'] = _commute_warnings
        if not _commute_warnings:
            print("  ✅ Ingen commute-parring-fejl i dag")
    except Exception as _e:
        print(f"  ⚠️ Commute-parring check fejlede: {_e}")
        data['commute_pairing_warnings'] = []

    # --- Check: har kommende events overhovedet trin? (gelænder 2026-07-22) ---
    # 22/7 stod et 16 km løb uden trin på uret kl. 06.35. Intervals bygger
    # træningen ud fra description — IKKE workout_doc. Prosa i description
    # giver en tom træning på uret uden nogen fejlmeddelelse nogen steder.
    try:
        from modules.event_structure import check_events as _check_struct
        _r_struct = api_get(f'{BASE}/events', auth=AUTH,
            params={'oldest': str(today), 'newest': str(today + timedelta(days=14))})
        _future = _r_struct.json() if _r_struct and _r_struct.status_code == 200 else []
        _struct_warnings = _check_struct(_future if isinstance(_future, list) else [])
        data['event_structure_warnings'] = _struct_warnings
        if _struct_warnings:
            for _w in _struct_warnings:
                print(f"  ⚠️ Event-struktur {_w['date']} '{_w['name']}' — {_w['code']}: {_w['text']}")
        else:
            print("  ✅ Alle events de næste 14 dage har trin")
    except Exception as _e:
        print(f"  ⚠️ Event-struktur-check fejlede: {_e}")
        data['event_structure_warnings'] = []

    # --- Push data.json ---
    if not gh_put('data.json', sha_data,
                  json.dumps(data, indent=2, ensure_ascii=False),
                  f'KPI auto-opdatering {today}'):
        print("❌ gh_put data.json fejlede — afbryder med exit 1 så Actions-kørslen bliver RØD")
        sys.exit(1)

    # --- Plan-view (fase 2): Friel-flags + kalibreret CTL-projektion ---
    # Hash-guard i modulet: skriver kun ved ændret plan.json eller ny fitness.
    try:
        from modules.plan_view import update_plan_view
        from modules.sessions import get_activities_since
        # T1: wellness -> readiness-gate. T3: 10-dages rå aktiviteter -> adaptation.
        _acts_10d = get_activities_since(10)
        update_plan_view(fitness, wellness, activities=_acts_10d)
    except Exception as _e:
        print(f"  ⚠️ plan_view fejlede (ikke-blokerende): {_e}")

    # --- Opdater kpis[] i index.html ---
    sha_html, html = gh_get('index.html')
    if html:
        lines = ['kpis:[']
        kpis_list = [
            ('VÆGT',      data['kpis']['weight']),
            ('FEDT%',     data['kpis']['fat']),
            ('CTL',       data['kpis']['ctl']),
            ('TSS COMP.', {'value': fmt(compliance,0) if compliance else '—', 'unit': '%' if compliance else '', 'sub': f"Planlagt {int(planned)} TSS", 'color': color_for(compliance, 85, lower=False) if compliance else '#7A6A58'}),
            ('HRV',       data['kpis']['hrv']),
            ('LØB KM',    data['kpis']['runKm']),
        ]
        for label, k in kpis_list:
            lines.append(f'    {{label:"{label}", value:"{k["value"]}", unit:"{k["unit"]}", sub:"{k["sub"]}", color:"{k["color"]}"}},')
        lines.append('  ]')
        kpis_block = '\n'.join(lines)
        import re as _re
        html = _re.sub(r'kpis:\[[\s\S]*?\]', kpis_block, html, count=1)
        # Bump version
        now = datetime.now().strftime("%Y%m%d-%H%M")
        html = _re.sub(r'<!-- v[\d\-]+ -->', f'<!-- v{now} -->', html)
        gh_put('index.html', sha_html, html, f'KPI kpis[] opdateret {today}')

    print("=== Done ===")

if __name__ == '__main__':
    try:
        main()
    except Exception as _fatal:
        import traceback
        err = traceback.format_exc()
        print(f'FATAL ERROR: {_fatal}')
        print(err)
        # Skriv fejl til en fil der kan pushes
        raise
















