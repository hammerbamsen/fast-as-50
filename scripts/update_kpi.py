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
                               PLAN, ACTIVE_PROGRAM, PROGRAM_ID, TOTAL_WEEKS,
                               DK_DAYS, DAY_SHORT, DK_MONTHS,
                               CTL_START, CTL_GOAL, AF_GOAL, SLEEP_GOAL_HOURS, GOALS,
                               api_get, ctl_plan_for_week, fix_enc, fmt, color_for)
from modules import programs as _programs
from modules.fitness  import get_fitness, get_wellness_7d, get_history, get_ctl_curve
from modules.aerobic  import get_ef_history
from modules import decoupling
from modules import checkin as _checkin
from modules import body as _body
from modules import ftp_track as _ftp
from modules.af       import (get_af_this_week, get_af_history, get_full_af_log,
                               get_af_streak, monday_this_week,
                               detect_alcohol_cluster)
from modules.sessions import (get_activities_week, get_workout_compliance_this_week,
                               format_compliance_for_prompt, get_planned_mins_this_week,
                               planned_tss_this_week, parse_planned_mins, calc_completion,
                               build_week_sessions, get_planned_weeks, generate_week_focus,
                               get_swim_history,
                               get_weekly_tss_actual)
import modules.coach as _coach_mod
from modules.coach    import (get_travel_label, weight_delta_vs_recent,
                               build_weight_context_note, build_trajectory_note,
                               qa_coach_speech, generate_coach_speech,
                               last_real_within)
from modules import coach_context as _coach_ctx
from modules import coach_validate as _coach_val
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


def sleep_kpi(sleep_history, fallback_avg=None, goal=None):
    """Søvn-KPI: (sidste nat, 7d-snit, sub-tekst, farve).

    sleep_history = [{date, v, real}, ...] (fitness.get_history). Værdien er
    seneste punkt med en værdi; snittet er de seneste 7 punkter med værdi.
    Farve måles på snittet: >=7,0 grøn, 6,5-7,0 orange, <6,5 rød.
    """
    goal = SLEEP_GOAL_HOURS if goal is None else goal
    vals = [float(r['v']) for r in (sleep_history or [])
            if isinstance(r, dict) and r.get('v') is not None]
    last = vals[-1] if vals else fallback_avg
    avg7 = round(sum(vals[-7:]) / len(vals[-7:]), 1) if vals else fallback_avg
    if avg7 is None:
        return last, None, f'Snit 7d — · mål {goal}t', '#7A6A58'
    color = '#27AE60' if avg7 >= 7.0 else ('#E67E22' if avg7 >= 6.5 else '#C0392B')
    return last, avg7, f'Snit 7d {fmt(avg7, 1)}t · mål {goal}t', color


def af_kpi(week_done, streak, af_history, goal):
    """AF DAGE-KPI: (sub-tekst, farve).

    sub = "af 6 denne uge · snit 4 uger X,X · streak N". 4-ugers snittet er
    de seneste 4 afsluttede uger (total == 7) i af_history; er der ingen
    afsluttede uger endnu, bruges det der findes.
    """
    hist = [w for w in (af_history or []) if isinstance(w, dict) and w.get('total')]
    full = [w for w in hist if w.get('total') == 7] or hist
    last4 = full[-4:]
    avg4 = round(sum(w['done'] for w in last4) / len(last4), 1) if last4 else None
    sub = f'af {goal} denne uge'
    if avg4 is not None:
        sub += f' · snit 4 uger {fmt(avg4, 1)}'
    if streak:
        sub += f' · streak {streak}'
    color = '#27AE60' if (week_done or 0) >= goal else '#59182A'
    return sub, color


def main():
    _sync_repo()
    today     = date.today()
    weekday   = today.weekday()
    # Uge/dag kommer fra det aktive program (programs.py) — ingen lokal clamp.
    week_num  = _programs.week_no(ACTIVE_PROGRAM, today)
    week_meta = _programs.week_meta(ACTIVE_PROGRAM, week_num)
    days_total = _programs.days_total(ACTIVE_PROGRAM)

    print(f"=== KPI opdatering {today} — {PROGRAM_ID} uge {week_num}/{TOTAL_WEEKS} "
          f"({week_meta.get('blockType', '?')}) ===")

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
    # Program + næste løb (på tværs af programmer) — erstatter daysToMedoc/
    # daysToChristiansborg, som var bundet til ét bestemt program.
    _upcoming = _programs.upcoming_races(PLAN, 'kennet', today)
    _next = _upcoming[0] if _upcoming else None
    data['meta'].pop('daysToMedoc', None)
    data['meta'].pop('daysToChristiansborg', None)
    data['meta']['nextRace']             = ({'name': _next.get('name'), 'date': _next.get('date'),
                                             'daysTo': _next.get('daysTo'),
                                             'priority': _next.get('priority', '')}
                                            if _next else None)
    data['meta']['programId']            = PROGRAM_ID
    data['meta']['programName']          = ACTIVE_PROGRAM.get('name')
    data['meta']['phase']                = week_meta.get('phase')
    data['meta']['blockType']            = week_meta.get('blockType')
    data['meta']['week']                 = week_num
    data['meta']['isoWeek']              = today.isocalendar()[1]
    data['meta']['totalWeeks']           = TOTAL_WEEKS
    data['meta']['programDay']           = _programs.program_day(ACTIVE_PROGRAM, today)
    data['meta']['programDays']          = days_total
    data['blockType']                    = week_meta.get('blockType') or 'BUILD'  # læses af coach-speech + index.html
    try:
        from modules.fitness import RHR_FIELD_SEEN
        data['meta']['rhrField'] = RHR_FIELD_SEEN.get('field')
    except Exception:
        data['meta']['rhrField'] = None
    data['ctlPlan']                      = CTL_PLAN
    data['blockTypes']                   = {str(k): v for k, v in BLOCK_TYPES.items()}   # periodisering i index.html
    data['goals']                        = GOALS                                           # programmets mål (svøm/løb-KPI'er)

    # --- Zoner: plan.json er master, dashboardet laeser dem herfra (28/7-2026) ---
    # index.html havde hardcodede fallbacks (260 sek/km, 270 W) og fulgte aldrig
    # med naar en test flyttede taersklen. Ikke-blokerende: fejler laesningen,
    # bevares den zones-blok der allerede stod i data.json.
    try:
        from pathlib import Path as _Path
        _plan_path = _Path(__file__).resolve().parent.parent / 'data' / 'plan.json'
        _zones = json.loads(_plan_path.read_text(encoding='utf-8'))['athletes']['kennet']['zones']
        data['zones'] = _zones
        print(f"  Zoner -> data.json: {_zones.get('runThreshold')} / {_zones.get('ftpW')} W")
    except Exception as _e:
        print(f"  Zoner kunne ikke laeses fra plan.json (ikke-blokerende): {_e}")

    # --- Mål (sættes FØR KPI-blokken bygges, da den læser disse felter) ---
    # --- Kommende løb med nedtælling til dashboardet ---
    #     Kilden er plan.json -> programs.*.races (aktivt + senere programmer).
    #     Hardkod dem aldrig i index.html.
    data['racesUpcoming'] = [
        {
            'name': r.get('name'),
            'date': r.get('date'),
            'days': r.get('daysTo'),
            'priority': r.get('priority', ''),
            'distance': r.get('distance', ''),
            'registered': r.get('registered'),
            'programId': r.get('programId'),
        }
        for r in _upcoming
    ]

    data['weightGoal']   = GOALS.get('weightKg', 68)
    data['bodyFatGoal']  = GOALS.get('bodyFatPct', 16)

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

    # Fedtprocent: samme "er den fra i DAG?"-logik. API-feltet er 'bodyFat'
    # (lowercase b) — 'Kropsfedt' er kun UI-navnet og findes ikke i API-svaret.
    def _field_today(rows, field):
        today_str = str(date.today())
        for row in (rows or []):
            dt = (row.get('id') or row.get('date') or '')[:10]
            if dt == today_str and row.get(field) is not None:
                return True
        return False
    fat_is_today = _field_today(_today_rows, 'bodyFat')

    # --- Fallback: seneste REELLE måling inden for 7 dage ---------------------
    # Nattekørslen rammer et tidspunkt hvor Garmin endnu ikke har synket dagens
    # vejning. Uden fallback fik coachen weight=None og skrev "ingen aktuel
    # vejning denne uge" -- selvom der lå målinger fra de foregående dage.
    # Datoen sendes ALTID med, så en gammel måling aldrig præsenteres som dagens.
    _last_real_within = last_real_within

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

    def _avg7_trend_note(avg_series, unit="point", window=7):
        """Retning ud fra 7-dages SNITTET: seneste snit vs. snittet `window` dage før.

        Erstatter den tidligere dag-til-dag-sammenligning. Et enkelt døgns udsving
        på en bioimpedansvægt er væske og målestøj -- ikke en tendens -- og fik
        coachen til at konkludere på ren støj. Snit-mod-snit filtrerer det væk.
        Returnerer None hvis der ikke er snit nok til en reel sammenligning.
        """
        idx = [i for i, v in enumerate(avg_series or []) if v is not None]
        if len(idx) < 2:
            return None
        i = idx[-1]
        j = next((k for k in reversed(idx) if k <= i - window), None)
        if j is None:
            return None
        raw = avg_series[i] - avg_series[j]
        days = i - j
        if abs(raw) < 0.1:  # tjek FØR afrunding -- ellers bliver 0,05 til "ned 0,1"
            return f"(7-dages snit uændret over de seneste {days} dage)"
        retning = 'op' if raw > 0 else 'ned'
        return (f"(7-dages snit {retning} {fmt(abs(raw))} {unit} over de seneste "
                f"{days} dage -- DETTE er den reelle retning)")

    weight_avg = wellness.get('weight_avg') if wellness else None
    fat        = wellness.get('fat')        if wellness else None

    # Værdier der sendes til coachen: dagens måling hvis den findes, ellers
    # seneste inden for 7 dage. *_coach_date er KUN sat når målingen ikke er
    # fra i dag -- det er det signal coach.py bruger til at skrive datoen med.
    _today_iso = str(date.today())
    if weight_is_today:
        weight_coach, weight_coach_date = weight, None
    else:
        weight_coach, weight_coach_date = _last_real_within((history or {}).get('weightHistory', []))
        if weight_coach_date == _today_iso:
            weight_coach_date = None
    if fat_is_today:
        fat_coach, fat_coach_date = fat, None
    else:
        fat_coach, fat_coach_date = _last_real_within((history or {}).get('fatHistory', []))
        if fat_coach_date == _today_iso:
            fat_coach_date = None
    print(f"  Coach-vægt: {weight_coach} kg (dato: {weight_coach_date or 'i dag'}) · "
          f"fedt: {fat_coach} % (dato: {fat_coach_date or 'i dag'})")
    protein    = wellness.get('protein')    if wellness else None
    hrv    = wellness.get('hrv_avg') if wellness else None
    rhr     = wellness.get('rhr')     if wellness else None
    rhr_avg = wellness.get('rhr_avg') if wellness else None
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
            weight_coach,
            (history or {}).get('weightHistory', [])
        )
        if trajectory_note:
            print(f"  Store billede (søndag): {trajectory_note}")

    # --- Vægt-KPI: behold sidste reelle måling som værdi, men vis DATOEN når
    # den ikke er fra i dag. Uden det læses en fremskrevet værdi som dagens tal
    # (fx 17.-22./7 under Mallorca, hvor 71,9 fra 16/7 stod og lignede aktuelt). ---
    def _last_real_weight_date(rows):
        for row in reversed(rows or []):
            if isinstance(row, dict) and row.get('v') is not None:
                return row.get('date')
        return None

    def _dk_short(iso):
        try:
            _y, _m, _d = str(iso)[:10].split('-')
            return f"{int(_d)}/{int(_m)}"
        except Exception:
            return None

    _w_goal_txt = f"Mål <{data['weightGoal']} kg"
    _w_avg_txt  = f" · snit {fmt(weight_avg)} kg" if weight_avg else ""
    if weight_is_today:
        weight_sub = _w_goal_txt + _w_avg_txt
    else:
        _lw_date = _dk_short(_last_real_weight_date((history or {}).get('weightHistory', [])))
        weight_sub = (f"Sidst målt {_lw_date} · {_w_goal_txt}{_w_avg_txt}"
                      if _lw_date else _w_goal_txt + _w_avg_txt)
    print(f"  Vægt-sub: {weight_sub} (måling i dag: {weight_is_today})")

    # --- Krop (blok 6, 6/9-2026): glidepath, fedt/FFM, cut-tjek -> data.body ---
    # Ren beregning i modules/body.py mod historikken + programmets weightPlan.
    # Styrke-loggen (28 dage) hentes her, så "styrke < 2 i to uger i træk" kan
    # tælles — all_weeks bærer ikke done-status for tidligere uger.
    _strength_log = data.get('strengthLog')
    try:
        _sl_oldest = today - timedelta(days=28)
        _r_sl = api_get(f'{BASE}/activities', auth=AUTH,
                        params={'oldest': str(_sl_oldest), 'newest': str(today)})
        if _r_sl is not None and _r_sl.status_code == 200:
            _strength_log = _body.strength_log_from_activities(_r_sl.json(), _sl_oldest, today)
            data['strengthLog'] = _strength_log
    except Exception as _e:
        print(f"  Styrke-log fejlede (ikke-blokerende, bruger cached): {_e}")
    # Blok 8: de 3 felter efter pas (rpe/complete/note/template) ligger i
    # plan.athletes.kennet.strengthLog (skrevet af plan-edit strength_log).
    # Flettes på dato; loggede dage uden aktivitet bliver session source 'log'.
    try:
        _plan_slog = (PLAN.get('athletes') or {}).get('kennet', {}).get('strengthLog') or {}
        if _strength_log:
            _strength_log = _body.merge_strength_log(_strength_log, _plan_slog)
            data['strengthLog'] = _strength_log
        data['strength'] = _body.build_strength(PLAN, _strength_log, today,
                                                templates=_body.load_workout_library(),
                                                target=int(GOALS.get('strengthPerWeek') or 2))
        _nx = data['strength']['next']
        _ck = data['strength'].get('checkin') or {}
        print(f"  Styrke: {len(_plan_slog)} loggede pas · næste {_nx['ab'].upper()} {_nx['templateId']} ({_nx['reasoning']}) · "
              f"{_nx.get('stateSummary')} · check-in {'DUE ' + str(_ck.get('date')) if _ck.get('due') else 'næste ' + str(_ck.get('next'))}")
    except Exception as _e:
        print(f"  Styrke-templates fejlede (ikke-blokerende): {_e}")
    # af_log hentes her (ét kald) så cut-tjekkets alkohol-signal ser dagens
    # registrering — genbruges i AF-log-afsnittet nedenfor.
    full_af_log = get_full_af_log()
    body = None
    try:
        _body_in = {
            'weightHistory': (history or {}).get('weightHistory') or data.get('weightHistory'),
            'fatHistory':    (history or {}).get('fatHistory')    or data.get('fatHistory'),
            'rhrHistory':    (history or {}).get('rhrHistory')    or data.get('rhrHistory'),
            'hrvHistory':    (history or {}).get('hrvHistory')    or data.get('hrvHistory'),
            'week_sessions': build_week_sessions(done_map, planned_weeks.get(week_num, {}).get('sessions', data.get('week_sessions', []))),
            'af_log':        full_af_log or data.get('af_log'),
        }
        body = _body.build_body(PLAN, _body_in, today, strength_log=_strength_log)
        data['body'] = body
        _g = body['glidepath']
        print(f"  Krop: fase {_g['phase']} · 7d {_g['avg7']} · forventet {_g['expectedKg']} · "
              f"status {_g['status']} · FFM {body['ffm']['now']} ({body['ffm']['change28d']:+} kg/28d)"
              if body['ffm']['change28d'] is not None else
              f"  Krop: fase {_g['phase']} · 7d {_g['avg7']} · forventet {_g['expectedKg']} · status {_g['status']}")
        print(f"  Cut-tjek: {body['cutCheck']['level']} — {body['cutCheck']['text']}")
    except Exception as _e:
        import traceback; traceback.print_exc()
        print(f"  Krop-modul fejlede (ikke-blokerende): {_e}")

    tss_color = color_for(compliance, 85, lower=False) if compliance else '#7A6A58'

    # Løb-km og svøm: mål findes KUN hvis det aktive program har dem i goals
    # (medoc-2026: runKmPerWeek/swimMeters; tds-2027: ingen -> neutral visning).
    # Farven måles mod SAMME tal som teksten viser — ikke et andet, skjult tal.
    _run_goal  = GOALS.get('runKmPerWeek')
    _swim_goal = GOALS.get('swimMeters')
    if _run_goal:
        _run_sub   = f'Mål {_run_goal}+ km/uge'
        _run_color = color_for(km_week, _run_goal, lower=False) if km_week else '#7A6A58'
    else:
        _run_sub   = 'Løb denne uge'
        _run_color = '#7A6A58'
    if _swim_goal:
        _swim_sub   = f'Svøm denne uge · mål {_swim_goal}m'
        _swim_color = color_for(swim_m, _swim_goal, lower=False) if swim_m else '#7A6A58'
    else:
        _swim_sub   = 'Svøm denne uge'
        _swim_color = '#7A6A58'
    # Søvn: værdi = sidste nats søvn (seneste sleepHistory-punkt med værdi),
    # sub = ægte 7-dages snit beregnet fra sleepHistory. Farve på snittet.
    sleep_last, sleep_avg7, _sleep_sub, _sleep_color = sleep_kpi(
        (history or {}).get('sleepHistory'), fallback_avg=sleep)
    print(f"  Søvn: sidste nat {sleep_last} · snit 7d {sleep_avg7}")

    # AF DAGE: værdi = AF-dage denne uge, sub = mål + 4-ugers snit fra
    # af_history, streak som lille hale. Hentes her (før kpis) — bruges igen nedenfor.
    af_history = get_af_history()
    _af_sub, _af_color = af_kpi(af_days, af_streak, af_history, AF_GOAL)

    # FTP mod fasemål (blok 13): W/kg på 7-dages vægt fra body.glidepath.
    _w7 = ((body or {}).get('glidepath') or {}).get('avg7') if body else None
    data['ftp'] = _ftp.build(PLAN, today, weight_avg7=_w7, week_num=week_num)

    data['kpis'] = {
        # Vægt/fedt: 7d-/14d-snit, sub + farve fra glidepath-status (body.py) —
        # ikke color_for mod slutmålet (det var rødt i fire måneder uanset retning).
        'weight':     (_body.weight_kpi(body) if body else
                       {'value': fmt(weight), 'unit': 'kg', 'sub': weight_sub, 'color': '#7A6A58'}),
        'fat':        (_body.fat_kpi(body) if body else
                       {'value': fmt(fat), 'unit': '%', 'sub': '14d-snit', 'color': '#7A6A58'}),
        'ctl':        {'value': fmt(ctl, 1),           'unit': '',   'sub': f"Uge {week_num}-mål {ctl_plan_for_week(week_num)} · {week_meta.get('blockType', '')}".rstrip(' ·'), 'color': color_for(ctl, ctl_plan_for_week(week_num), lower=False) if ctl else '#7A6A58'},
        'tsb':        {'value': fmt(tsb, 1),           'unit': '',   'sub': ('Hård blok · CTL−ATL, frisk >0' if tsb and tsb < -10 else 'Form · CTL−ATL, frisk >0'), 'color': '#E67E22' if tsb and tsb < -10 else '#27AE60'},
        'sleep':      {'value': fmt(sleep_last, 1) if sleep_last else '—', 'unit': 't', 'sub': _sleep_sub, 'color': _sleep_color},
        'runKm':      {'value': fmt(km_week, 1),       'unit': 'km', 'sub': _run_sub,                                   'color': _run_color},
        'hrv':        {'value': fmt(hrv, 1),           'unit': 'ms', 'sub': 'Snit 7d',                       'color': '#7A6A58'},
        'rhr':        {'value': fmt(rhr_avg, 0) if rhr_avg else '—', 'unit': 'slag', 'sub': 'Hvilepuls · snit 7d', 'color': '#7A6A58'},
        'tssComp':    {'value': fmt(tss_act, 0) if tss_act else '0', 'unit': 'TSS',
                       'sub': f'{int(tss_act or 0)} af {int(planned)} planlagt TSS',
                       'color': tss_color},
        'bikeKm':     {'value': fmt(bike_km, 1),       'unit': 'km', 'sub': 'Cykel denne uge',                  'color': color_for(bike_km, 50, lower=False) if bike_km else '#7A6A58'},
        'swimM':      {'value': fmt(swim_m, 0) if swim_m else '0',    'unit': 'm',  'sub': _swim_sub,                                  'color': _swim_color},
        'afStreak':   {'value': str(af_days),          'unit': '',   'sub': _af_sub,                                    'color': _af_color},
        'ftp':        _ftp.kpi(data['ftp']),
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

    # --- Cut-tjek (blok 6): erstatter den gamle RHR/HRV-cut-alarm. Én advarsel
    # (type 'cut') når body.cutCheck er warn/act — kun aktiv i fase 'cut'. ---
    _cut_w = _body.cut_warning(body) if body else None
    if _cut_w:
        warnings.append(_cut_w)

    data['warnings'] = warnings
    if warnings:
        print(f"  ⚠️  Advarsler: {[w['message'] for w in warnings]}")

    data['tsb'] = tsb  # direkte TSB-tal til brug i frontend advarsler
    data['weekTss'] = {'actual': tss_act, 'planned': planned}   # ugens TSS som tal (Martin-mail, blok 8)
    # --- AF-dage (man–søn denne uge) ---
    data['af'] = {
        'weekDone': af_days if af_days is not None else data.get('af', {}).get('weekDone', 0),
        'target': AF_GOAL,
        'streak': af_streak
    }

    # --- AF log: dag-for-dag til index.html's log-ark (af.html slettet blok 9) (alle uger siden projektstart) ---
    # (full_af_log hentet ovenfor, før krop-modulet.)
    if full_af_log:
        data["af_log"] = full_af_log
        print(f"  AF log (alle dage): {len(full_af_log)} dage")

        # Klynge-advarsel: to eller flere drikkedage i træk rammer HRV
        # hårdere end samme antal dage spredt ud (verificeret 31/7-2/8-2026,
        # hvor tre dage i træk gav sæsonens to laveste HRV-tal).
        cluster = detect_alcohol_cluster(full_af_log)
        if cluster:
            _c_start = _dk_short(cluster['start'])
            _c_end   = _dk_short(cluster['end'])
            _span    = f"{_c_start}–{_c_end}" if _c_start and _c_end else ""
            warnings.append({
                'type':    'alcohol_cluster',
                'level':   'critical' if cluster['days'] >= 3 else 'warn',
                'message': (f"{cluster['days']} drikkedage i træk {_span} — "
                            f"klynger rammer HRV hårdere end spredte dage."),
            })
            data['warnings'] = warnings
            print(f"  ⚠️  Alkohol-klynge: {cluster}")

    # --- AF historik: uge-for-uge siden projektstart (hentet ovenfor til AF-KPI'en) ---
    if af_history:
        data['af_history'] = af_history

    # --- Check-in-log (alkohol/protein/energi/aftensult) sidste 28 dage ---
    # Samme wellness-kilde som af_log. Bruges af I dag-fanens log-ark (7 prikker),
    # Krop-fanens protein-kort og én linje i coach-prompten. af_log holder sig til
    # 0/1 (index.html læser det); hvordan drikkedagen blev registreret
    # (valgt/autopilot) ligger i checkinLog.alkohol (1/2) og i af_kind.
    checkin_log = _checkin.get_checkin_log()
    data['checkinLog'] = checkin_log
    data['kpis']['protein'] = _checkin.protein_kpi(checkin_log)
    data['energy7'] = _checkin.energy_avg(checkin_log, 7)
    data['af_kind'] = _checkin.af_kinds(checkin_log)
    checkin_line = _checkin.coach_line(checkin_log)
    if checkin_line:
        print(f"  Check-in: {checkin_line}")

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
        if history.get('rhrHistory'):    data['rhrHistory']    = history['rhrHistory']
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

    def _latest_avg(series):
        """Seneste ikke-None værdi i en 7-dages snit-serie (None hvis serien er tom)."""
        return next((v for v in reversed(series or []) if v is not None), None)

    # weightToGoal/bodyFatToGoal (afstand til slutmålet) er fjernet 6/9-2026 —
    # Krop-fanen måler mod glidepath'en (data.body), ikke mod 68 kg.
    data.pop('weightToGoal', None)
    data.pop('bodyFatToGoal', None)
    if ctl_curve:
        data['ctlCurve'] = ctl_curve

    # --- Historisk faktisk TSS pr. uge (backfill til Excel + ugesummer) ---
    try:
        _wk_tss = get_weekly_tss_actual(date.fromisoformat(ACTIVE_PROGRAM['start']), TOTAL_WEEKS)
        if _wk_tss:
            data['weekTssActual'] = {str(k): v for k, v in sorted(_wk_tss.items())}
            print(f"  weekTssActual -> {len(_wk_tss)} uger")
        else:
            print("  weekTssActual: tomt svar — beholder eksisterende")
    except Exception as _e:
        print(f"  weekTssActual fejlede (ikke-blokerende): {_e}")
        print(f"  CTL-kurve: {len(ctl_curve)} ugepunkter, seneste {ctl_curve[-1]}")
    if swim_history:
        data['swimHistory'] = swim_history

    # --- Aerob effektivitet (EF): formsignal mellem tærskeltests ---
    # Ikke-blokerende: fejler kaldet, beholdes den eksisterende serie frem for
    # at nulstille grafen. Samme mønster som weekTssActual ovenfor.
    # --- Aerobt flag på seneste pas ---
    # Samme EF-tal, kortere horisont: trenden svarer på "hvordan går det over 42
    # dage", flaget på "hvad kostede passet i går". Punkterne lå allerede i
    # efHistory — de blev bare aldrig læst enkeltvis.
    decoupling_note = None
    try:
        _ef = get_ef_history(days=180)
        if _ef:
            data['efHistory'] = _ef['history']
            data['efTrend']   = _ef['trend']
            _flag = decoupling.latest(_ef.get('acts'), _ef['history'])
            if _flag:
                data['aerobicFlag'] = _flag
                decoupling_note = decoupling.format_note(_flag)
                print(f"  Aerobt flag: {_flag['date']} {_flag['discipline']} "
                      f"{_flag['pct']:+.1f}% ({_flag['level']})")
            else:
                # Intet sammenligneligt pas inden for 2 dage: fjern et gammelt
                # flag frem for at lade det stå og se dagsaktuelt ud.
                data.pop('aerobicFlag', None)
                print("  Aerobt flag: intet sammenligneligt pas de seneste 2 dage")
    except Exception as _e:
        print(f"  EF fejlede (ikke-blokerende): {_e}")

    # --- all_weeks: forrige/denne/næste uge fra Intervals ---
    if planned_weeks:
        # Merge done_map ind i denne uges sessions
        this_week = planned_weeks.get(week_num, {})
        if this_week:
            this_week['sessions'] = build_week_sessions(done_map, this_week['sessions'])
            _focus_cached_week = data.get('weekFocusWeek')
            _focus_cached_text = data.get('weekFocus', '')
            _focus_next = data.get('weekFocusNext') or {}
            if _focus_cached_week == week_num and _focus_cached_text:
                print(f"  weekFocus cached (uge {week_num})")
                dynamic_focus = _focus_cached_text
            elif (_focus_next.get('week') == week_num and _focus_next.get('programId') == PROGRAM_ID
                  and _focus_next.get('text')):
                # Søndagens coach v2-kørsel lagde fokus for denne uge
                dynamic_focus = _focus_next['text']
                data['weekFocusWeek'] = week_num
                print(f"  weekFocus fra søndagens gennemgang: {dynamic_focus}")
            else:
                # Regelbaseret indtil coach v2 (mandag) leverer ugefokus — det
                # separate AI-kald (generate_week_focus_ai) er fjernet 6/9-2026.
                dynamic_focus = generate_week_focus(
                    week_num, this_week.get('sessions', []),
                    BLOCK_TYPES.get(week_num, 'BUILD'))
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

    # --- Plan-fanen (blok 4): data.planTab — uge −1..+7, pas pr. dag, CTL, hårde pas ---
    # Ikke-blokerende: fejler den, beholdes den eksisterende planTab i data.json.
    try:
        from modules.plan_tab import build_plan_tab
        from modules.fitness import get_ctl_daily
        _pv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'plan_view.json')
        try:
            with open(_pv_path, encoding='utf-8') as _fh:
                _plan_view = json.load(_fh)
        except Exception:
            _plan_view = None
        _ctl_daily = get_ctl_daily() or {}
        data['planTab'] = build_plan_tab(
            PLAN, _plan_view, data.get('week_sessions', []), data.get('all_weeks', {}), today,
            week_tss_actual=data.get('weekTssActual'), ctl_daily=_ctl_daily)
        print(f"  planTab -> {len(data['planTab']['weeks'])} uger, "
              f"{sum(len(d['entries']) for s in data['planTab']['sessions'] for d in s['days'])} pas, "
              f"{len(data['planTab']['hardSpacing'])} hårde par")
    except Exception as _e:
        print(f"  planTab fejlede (ikke-blokerende): {_e}")

    # --- Martin-mail (blok 8): de 8 linjer til søndagsmailen -> data.martinMail
    # hver kørsel. Om søndagen appendes afsnittet "### Signaler uge {iso}" til
    # data/martin_signals.md én gang (gh_get/gh_put, ikke-blokerende).
    try:
        from modules import martin_signals as _ms
        _ms_sha, _ms_raw = gh_get('data/martin_signals.md')
        data['martinMail'] = _ms.build_weekly(data, PLAN, today, signals_md=_ms_raw)
        print(f"  Martin-mail uge {data['martinMail']['isoWeek']}: {data['martinMail']['lines'][0]}")
        if weekday == 6:
            _iso = data['martinMail']['isoWeek']
            if _ms_raw is None:
                print("  Martin-signaler: martin_signals.md kunne ikke hentes — intet appendet")
            elif _ms.has_weekly(_ms_raw, _iso):
                print(f"  Martin-signaler uge {_iso} står allerede i martin_signals.md")
            else:
                gh_put('data/martin_signals.md', _ms_sha,
                       _ms.append_signal(_ms_raw or '', _ms.format_weekly(data['martinMail'])),
                       f"martin: signaler uge {_iso}")
    except Exception as _e:
        print(f"  Martin-mail fejlede (ikke-blokerende): {_e}")

    # --- Forslag (blok 9): data/proposals/*.json med status pending -> data.proposals
    # (before = nuværende plan, after = forslaget, pr. ISO-uge). Tomt array når ingen.
    data['proposals'] = []
    try:
        from modules import proposals as _props
        data['proposals'] = _props.build_data_proposals(PLAN)
        print(f"  Forslag: {len(data['proposals'])} afventer"
              + (" — " + ", ".join(p['id'] for p in data['proposals']) if data['proposals'] else ""))
    except Exception as _e:
        print(f"  Forslag fejlede (ikke-blokerende): {_e}")

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
        ctl=ctl, tsb=tsb, weight=weight_coach, sleep=sleep, compliance=compliance,
        tss_act=tss_act, planned=planned, week_sessions=data['week_sessions'],
        travel_note=context_note, trajectory_note=trajectory_note, days_completed=days_completed,
        decoupling_note=decoupling_note,
        weight_goal=data['weightGoal'], weight_date=weight_coach_date
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
    #
    # COACH_FORCE (23/7-26): cachen brydes udelukkende af DATA-ændringer (vægt,
    # fedt, AF, aktivitet, plan). Der var ingen måde at sige "giv mig en frisk
    # vurdering NU". Trykkede Kennet på ↻ i dashboardet 2 timer efter sidste
    # generering, kørte workflowet fint igennem, sprang AI-kaldet over, og
    # knappen så ødelagt ud. Manuelt tryk sætter nu COACH_FORCE=1 hele vejen
    # gennem Worker -> client_payload -> workflow-env og tvinger en generering.
    # Intervals-webhooken sætter den IKKE — automatiske kørsler respekterer
    # stadig de 6 timer, så vi ikke brænder AI-kald på hver eneste aktivitet.
    CACHE_FORCE = os.environ.get('COACH_FORCE', '').strip().lower() not in ('', '0', 'false', 'no')
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

    # Ny fedtmåling skal ALTID bryde cachen — ellers kan en frisk måling
    # ligge i data uden at coachen nogensinde reagerer på den.
    _fat_at_gen = data.get('coachAssessmentFatAtGen')
    _fat_changed = (
        fat is not None
        and (_fat_at_gen is None or abs(fat - _fat_at_gen) > 0.05)
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

    # --- Coach v2 (6/9-2026): kontekst som data, regler i prompts/*.md,
    #     struktureret svar via tool-use, mekanisk validering. Ét kald pr.
    #     generering — ugefokus (søndag/mandag) kommer med i samme svar.
    _coach_prev = data.get('coach') if isinstance(data.get('coach'), dict) else {}
    _ctx = None
    _ctx_hash = None
    try:
        _ctx = _coach_ctx.build_context(
            PLAN, data, today,
            ctl=ctl, atl=atl, tsb=tsb, wellness=wellness,
            weight=weight_coach, fat=fat_coach, weight_date=weight_coach_date, fat_date=fat_coach_date,
            planned_tss=planned, tss_actual=tss_act, af_streak=af_streak,
            travel_label=travel_label)
        _ctx_hash = _coach_ctx.inputs_hash(_ctx)
    except Exception as _e:
        import traceback; traceback.print_exc()
        print(f"  ⚠️  coach-kontekst fejlede: {_e}")

    # Mandag uden ugefokus for denne uge -> generér uanset cache
    _focus_missing = (weekday == 0 and data.get('weekFocusWeek') != week_num)
    _hash_same = (_ctx_hash is not None and _coach_prev.get('inputsHash') == _ctx_hash)

    _cache_fresh = (_cache_age_h is not None and _cache_age_h < CACHE_HOURS
                    and not _weight_changed and not _fat_changed and not _af_changed
                    and not _activity_changed and not _plan_changed and not _focus_missing)
    ai_answer, ai_info = None, {}
    if _ctx is None:
        pass
    elif not CACHE_FORCE and (_cache_fresh or _hash_same) and _coach_prev.get('oneThing'):
        _why = "uændret kontekst" if _hash_same else f"{_cache_age_h:.1f}t gammel"
        print(f"  Coach-vurdering cached ({_why}) -- springer AI-kald over")
    else:
        if CACHE_FORCE:
            _age_txt = f"{_cache_age_h:.1f}t" if _cache_age_h is not None else "ukendt"
            print(f"  COACH_FORCE sat (cache {_age_txt} gammel) -- tvinger frisk AI-vurdering")
        if _weight_changed:
            print(f"  Ny vejning ({_weight_at_gen} -> {weight}) -- bryder cache tidligt")
        if _fat_changed:
            print(f"  Ny fedtmåling ({_fat_at_gen} -> {fat}) -- bryder cache tidligt")
        if _af_changed:
            print(f"  AF-status ændret ({_af_at_gen} -> {af_this_week}) -- bryder cache tidligt")
        if _activity_changed:
            print(f"  Ny aktivitet ({_last_act_id_at_gen} -> {_latest_act_id}) -- bryder cache tidligt")
        if _focus_missing:
            print("  Mandag uden ugefokus -- bryder cache")
        ai_answer, ai_info = _coach_mod.generate_coach_v2(_ctx, ANTHROPIC_KEY)

    if ai_answer:
        program_day = _programs.program_day(ACTIVE_PROGRAM, date.today())
        header_str = f"Dag {program_day} af {days_total} · {DK_DAYS[weekday]} · Uge {week_num}"
        _now_utc = datetime.utcnow().replace(microsecond=0)
        _merged = _coach_val.merge_warnings(warnings, ai_answer.get('warnings'))
        data['coach'] = {
            'generatedAt': _now_utc.isoformat() + 'Z',
            'inputsHash': _ctx_hash,
            'model': ai_info.get('model'),
            'mode': _coach_mod.coach_mode(weekday),
            'oneThing': ai_answer['oneThing'],
            'training': ai_answer['training'],
            'body': ai_answer['body'],
            'habits': ai_answer['habits'],
            'bigPicture': ai_answer['bigPicture'],
            'weekFocus': ai_answer.get('weekFocus'),
            'weekFocusFor': (week_num + 1 if weekday == 6 else week_num) if ai_answer.get('weekFocus') else None,
            'warnings': _merged,
            'error': None,
            'validationError': None,
            'notes': ai_info.get('notes'),
            'stale': False,
        }
        # Gamle felter udfyldes fra det nye svar, så index.html/plan.html ikke knækker
        coach_speech, coach_highlight = _coach_mod.legacy_fields(ai_answer)
        data['coachSpeech']    = coach_speech
        data['coachHighlight'] = coach_highlight
        data['coachAssessmentHtml']        = _coach_mod.render_assessment_html(ai_answer, header_str)
        data['coachAssessmentTs']          = now_cph.strftime('%H:%M')
        data['coachAssessmentTsFull']      = _now_utc.isoformat()
        data['coachAssessmentWeightAtGen'] = weight if weight is not None else _weight_at_gen
        data['coachAssessmentFatAtGen']    = fat if fat is not None else _fat_at_gen
        data['coachAssessmentAfAtGen']     = af_this_week
        data['coachAssessmentLastActId']   = _latest_act_id
        data['coachAssessmentPlanAtGen']   = _today_label
        data['coachAssessmentError'] = None
        # Legacy warnings: regel-advarsler + AI-advarsler (act -> critical)
        _lvl_legacy = {'act': 'critical', 'warn': 'warn', 'info': 'info'}
        data['warnings'] = [dict(w, level=_lvl_legacy.get(w['level'], w['level'])) for w in _merged]
        # Ugefokus fra samme kald: mandag = denne uge, søndag = næste uge
        _wf = ai_answer.get('weekFocus')
        if _wf and weekday == 0:
            data['weekFocus'] = _wf
            data['weekFocusWeek'] = week_num
            if str(week_num) in data.get('all_weeks', {}):
                data['all_weeks'][str(week_num)]['focus'] = _wf
        elif _wf and weekday == 6:
            _next_wk = week_num + 1
            _next_pid = PROGRAM_ID
            _np = _programs.active_program(PLAN, 'kennet', today + timedelta(days=1))
            if _np and _np.get('id') != PROGRAM_ID:
                _next_pid, _next_wk = _np['id'], _programs.week_no(_np, today + timedelta(days=1))
            data['weekFocusNext'] = {'week': _next_wk, 'programId': _next_pid, 'text': _wf}
            if _next_pid == PROGRAM_ID and str(_next_wk) in data.get('all_weeks', {}):
                data['all_weeks'][str(_next_wk)]['focus'] = _wf
    else:
        # Behold eksisterende (cache stadig frisk, eller API/validering fejlede)
        if not data.get('coachAssessmentHtml'):
            data['coachAssessmentHtml'] = ''
            data['coachAssessmentTs']   = ''
        _ai_err = getattr(_coach_mod, 'LAST_AI_ERROR', None)
        data['coachAssessmentError'] = _ai_err
        if _coach_prev:
            data['coach'] = dict(_coach_prev)
            data['coach']['error'] = _ai_err
            data['coach']['validationError'] = ai_info.get('validationError')
            data['coach']['stale'] = bool(_ctx_hash and _coach_prev.get('inputsHash') != _ctx_hash)
        else:
            data['coach'] = {'generatedAt': None, 'inputsHash': None, 'model': None, 'oneThing': None,
                             'training': None, 'body': None, 'habits': None, 'bigPicture': None,
                             'weekFocus': None, 'warnings': _coach_val.merge_warnings(warnings, None),
                             'error': _ai_err, 'validationError': ai_info.get('validationError'), 'stale': True}
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

    # index.html's D.kpis er kun fallback — applyRemote() læser kpis fra data.json.
    # Den gamle regex-erstatning af kpis:[...] + push af index.html er fjernet 3/9-2026.

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
















