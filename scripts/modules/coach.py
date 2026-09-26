"""Coach-tekst, AI-assessment og QA-logik."""
import os, re, json, urllib.request as _urllib_req
from datetime import date, timedelta
from .config import (PLAN, ACTIVE_PROGRAM, GOALS, TOTAL_WEEKS, BASE, AUTH, api_get, fix_enc, fmt, ctl_plan_for_week, ANTHROPIC_KEY,
                      DK_DAYS, DK_MONTHS, DAY_SHORT,
                      CTL_START, CTL_GOAL, AF_GOAL, SLEEP_GOAL_HOURS, athlete_age)
from . import programs as _programs

# Blok-typer hvor lav TSS er planen (blok 9): ingen TSS-andels-linjer i teksten.
LOW_LOAD_BLOCKS = ('RACE', 'RECOVERY', 'TAPER')


def weeks_to_next_race(today=None):
    """Hele uger til næste løb på tværs af programmerne (None hvis intet løb forude)."""
    today = today or date.today()
    up = _programs.upcoming_races(PLAN, "kennet", today) if PLAN else []
    if not up:
        return None, None
    return max(0, round(up[0]["daysTo"] / 7)), up[0]

QUOTES_TRAINING = [
    "\"Det er ikke om at have tid. Det er om at tage den.\"",
    "\"Sæt farten ned, så du kan gå langt.\"",
    "\"Konsistens slår intensitet, hver gang.\"",
    "\"Hvil er ikke det modsatte af fremskridt — det er en del af det.\"",
    "\"Formen bygges i kedsomheden — ikke i begejstringen.\"",
    "\"Et program er lang tid. Men hver dag er kort.\"",
    "\"Den bedste træning er den, du faktisk gennemfører.\"",
    "\"Recovery er ikke pause — det er produktion.\"",
    "\"Du har gjort det 16 gange før. Kroppen kender vejen.\"",
]

QUOTES_DIET = [
    "\"Et godt måltid og en god nats søvn slår en ekstra hård træning.\"",
    "\"AF-dage er ikke et offer — de er en investering i morgendagens energi.\"",
    "\"Mindre alkohol, mere søvn — den billigste performance-boost der findes.\"",
    "\"Protein ved hvert måltid. Ingen undtagelser, ingen drama.\"",
    "\"Kroppen tror, hvad sindet siger.\"",
    "\"Vægten flytter sig ikke i dag. Men vanen gør.\"",
]

QUOTES_PHILOSOPHY = [
    "\"Disciplin er at vælge mellem hvad du vil nu, og hvad du vil mest.\"",
    "\"Det er de små valg hver dag, der bygger den store form.\"",
    "\"Keep moving forward.\"",
    "\"Du konkurrerer ikke mod andre i dag. Kun mod gårsdagens dig.\"",
    "\"Smertegrænsen flytter sig — men kun hvis du respekterer den først.\"",
    "\"Sæt målet højt, men sæt i dag realistisk.\"",
    "\"Form kommer og går. Vaner bliver.\"",
    "\"Hold roen. Hold rytmen. Hold farten.\"",
    "\"Du har magt over dit sind — ikke over yderomstændigheder. Indse det, og du finder styrke.\" — Marcus Aurelius",
    "\"Begynd ikke at handle som om du har ti tusind år at leve i.\" — Marcus Aurelius",
    "\"Hindringen for handling fremmer handlingen. Det, der står i vejen, bliver vejen.\" — Marcus Aurelius",
    "\"Det er ikke at have for lidt, der gør et menneske fattigt, men at ville have mere.\" — Seneca",
    "\"Hver morgen: jeg vågner for at gøre menneskets arbejde.\" — Marcus Aurelius",
    "\"Udholdenhed er bitter, men dens frugt er sød.\"",
    "\"Du bliver til det, du gør ofte.\"",
]


# ── Distance-bevidst completion (rettet 7/8-2026) ────────────────────────
# Udtrukket som selvstændige funktioner så de kan testes uden at kalde
# Anthropic-API'et eller bygge en fuld week_sessions-liste.

def _dist_pair(actual, planned, disc):
    """Formaterer 'faktisk af planlagt' i den enhed disciplinen måles i.
    Svøm beholder den nøjagtige meter-formulering fra 7/8-2026 — den var korrekt
    og er ikke rørt. Løb og cykel er nye her (8/8-2026): da km-mål blev indført,
    nåede de her funktioner discipliner de aldrig var skrevet til, og et løb ville
    være blevet beskrevet som '21000 af 29000m'."""
    if disc in ('swim', 'openwater') or disc is None:
        return f"{int(actual)} af {int(planned)}m"
    _km = lambda v: f"{v / 1000:.1f}".replace('.', ',')
    return f"{_km(actual)} af {_km(planned)} km"


def build_distance_focus_line(today_session, shortfall_threshold=0.80):
    """Returnerer en fokus-sætning til den hårdkodede coach-tekst hvis dagens
    session har et eksplicit distance-mål og landede under shortfall_threshold
    af det — ellers None (intet mål, ingen data, eller målet er nået)."""
    if not today_session:
        return None
    planned = today_session.get('planned_distance_m')
    actual = today_session.get('actual_distance_m')
    if not planned or planned <= 0:
        return None
    if actual is None:
        return None  # ingen data -- undgå falsk flag på datahul
    pct = actual / planned
    if pct >= shortfall_threshold:
        return None  # målet nået -- intet at fokusere på
    label = today_session.get('label', 'Dagens pas')
    pair = _dist_pair(actual, planned, today_session.get('disc'))
    return (f"{label}: {pair} ({round(pct * 100)}%) — "
            f"distancen er under målet, selvom passet tæller som gennemført.")


def build_distance_prompt_line(today_session):
    """AI-prompt-variant: samme grundlag, men altid med tal (også når målet ER
    nået), så AI-vurderingen har korrekt kontekst uanset udfald — plus en
    eksplicit instruks om at nævne det hvis under 80%."""
    if not today_session:
        return ""
    planned = today_session.get('planned_distance_m')
    actual = today_session.get('actual_distance_m')
    if not planned or planned <= 0 or actual is None:
        return ""
    pct = round(actual / planned * 100)
    pair = _dist_pair(actual, planned, today_session.get('disc'))
    return (
        f"\n- DISTANCE i dag: {pair} planlagt ({pct}%). "
        f"Gengiv disse tal PRÆCIS som de står — rund ikke af. "
        f"Nævn dette EKSPLICIT i vurderingen hvis under 80%, uanset om passet "
        f"tæller som gennemført i systemet — registreret/gennemført er IKKE "
        f"det samme som at distancen er ramt."
    )


def get_travel_label(today_str):
    """Læs data/travel_days.json og returner en KORT rejse-label for i dag (eller
    None) — uden nogen antagelse om hvilken retning vægten har bevæget sig.
    Listen vedligeholdes manuelt (typisk i søndagsrutinen ud fra Outlook-
    kalenderen) — scriptet selv har ikke live kalenderadgang."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'travel_days.json')
    try:
        with open(path, encoding='utf-8') as f:
            trips = json.load(f).get('trips', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    for trip in trips:
        if trip.get('travel_home_date') == today_str:
            return trip.get('label_home') or f"dagen efter hjemrejse fra {trip.get('label', 'rejse')}"
        start, end = trip.get('start'), trip.get('end')
        if start and end and start <= today_str <= end:
            return trip.get('label_during') or f"midt i {trip.get('label', 'rejse')}"
    return None


def weight_delta_vs_recent(weight_history, today_str, weight_today):
    """Sammenlign dagens reelle vægt med seneste forudgående REELLE måling (ikke en
    fremført/fyldt værdi). Returnerer (delta, dato) eller (None, None)."""
    if weight_today is None or not weight_history:
        return None, None
    prior_real = [h for h in weight_history if h is not None and isinstance(h, dict) and h.get('real') and h.get('date') != today_str]
    if not prior_real:
        return None, None
    prior = prior_real[-1]
    if prior.get('v') is None:
        return None, None
    return round(weight_today - prior['v'], 1), prior['date']


def build_weight_context_note(travel_label, delta, prior_date, threshold=0.8):
    """Kombinerer rejse-label og FAKTISK vægt-delta til én note. Kritisk: 'sandsynligvis
    væske/retention'-sproget bruges KUN når vægten reelt er steget — en rejsedag-label
    må aldrig i sig selv få coachen til at påstå retention hvis vægten faktisk er faldet
    eller uændret. Bruges både til den hårdkodede coachSpeech og AI-prompten."""
    if delta is None:
        return None
    suffix = f", {travel_label}" if travel_label else ""
    if delta >= threshold:
        return (f"Vægten er {delta} kg højere end seneste måling ({prior_date}){suffix} — "
                f"sandsynligvis væske/natrium snarere end fedt, ikke et disciplinproblem. "
                f"Giv den et par dage før du dømmer tallet.")
    if delta <= -threshold and travel_label:
        return (f"Vægten er allerede {abs(delta)} kg lavere end seneste måling ({prior_date}) "
                f"({travel_label}) — ser ud til at have normaliseret sig hurtigt. Godt tegn.")
    return None



def build_bike_library_line(weekday, week_ids=None):
    """Kaelder-katalog til soendagens check-in.

    Soendag er dagen hvor de kommende 14 dages kaelderpas laegges. Uden
    kataloget i prompten opfinder modellen sine egne pas, og saa er
    biblioteket bare 20 filer der ligger og stoever. Med det skal den
    vaelge et id fra listen.

    weekday: 0=mandag ... 6=soendag (samme konvention som resten af coach.py)
    week_ids: valgte workout-id'er for ugen — valideres mod reglerne.
    """
    if weekday != 6:
        return ""
    try:
        from . import bike_library
    except ImportError:  # koert som script uden pakke-kontekst
        import bike_library
    try:
        lib = bike_library.load()
    except (IOError, OSError, ValueError):
        return ""
    cats = bike_library.meta(lib)["categories"]
    rules = bike_library.meta(lib)["rules"]
    lines = []
    for key, label in cats.items():
        ws = bike_library.by_category(key, lib)
        if not ws:
            continue
        items = ", ".join("%s (%d min, %s)" % (w["id"], w["est_min"], w["load"]) for w in ws)
        lines.append("  %s: %s" % (label, items))
    out = (
        "\n- KAELDER-KATALOG (obligatorisk kilde til indendoers cykelpas): "
        "vaelg altid et id herfra, opfind aldrig et nyt pas.\n" + "\n".join(lines) +
        "\n  Regler: max %d haarde og %d moderate cykelpas pr. uge, mindst %d timer "
        "mellem to haarde." % (rules["maxHaardPerWeek"], rules["maxModeratPerWeek"],
                               rules["minHoursBetweenHaard"])
    )
    if week_ids:
        warn = bike_library.check_week(list(week_ids), lib)
        if warn:
            out += "\n  ADVARSEL paa den foreslaaede uge: " + " | ".join(warn)
    return out

def build_trajectory_note(week_num, ctl, weight, weight_history):
    """Bygger en 'store billede'-sætning til den UGENTLIGE opsummering (søndage) —
    i modsætning til den daglige tekst, som kun ser på i dags snapshot, kigger denne
    på CTL-pace mod den rigtige (recovery-justerede) ugeplan og vægtens udvikling
    over de seneste uger. Returnerer None hvis der ikke er nok data."""
    parts = []

    if ctl is not None and week_num:
        plan_target = ctl_plan_for_week(week_num)
        delta = round(ctl - plan_target, 1)
        if delta >= 0:
            parts.append(f"CTL {fmt(ctl,1)} er {delta} point FORAN ugeplanen (planmål uge {date.today().isocalendar()[1]}: {plan_target}).")
        else:
            parts.append(f"CTL {fmt(ctl,1)} er {abs(delta)} point BAG ugeplanen (planmål uge {date.today().isocalendar()[1]}: {plan_target}).")

    if weight is not None and weight_history:
        reals = [h for h in weight_history if isinstance(h, dict) and h.get('real') and h.get('v') is not None]
        if len(reals) >= 2:
            earliest = reals[0]
            try:
                days = (date.today() - date.fromisoformat(earliest['date'])).days
            except ValueError:
                days = None
            w_delta = round(weight - earliest['v'], 1)
            if days and days >= 7 and abs(w_delta) >= 0.3:
                retning = "tabt" if w_delta < 0 else "taget på"
                parts.append(f"Vægten har {retning} {abs(w_delta)} kg over de seneste {days} dage ({fmt(earliest['v'])} → {fmt(weight)} kg).")

    return " ".join(parts) if parts else None


def _goal(value, key, fallback):
    """Mål fra det aktive programs goals (plan.json) når kalderen ikke giver et."""
    if value is not None:
        return value
    return (GOALS or {}).get(key, fallback)


def qa_coach_speech(speech, week_sessions, ctl, tsb, weight, af_this_week, tss_act, planned, weight_goal=None):
    weight_goal = _goal(weight_goal, 'weightKg', 68)
    """QA-tjek: returner liste af fejl hvis coach-teksten modsiger de faktiske data.
    Bruges til at stoppe en forkert tekst fra at gå live.

    Regler:
    1. Nævn aldrig en session som manglende hvis den er done=True i week_sessions
    2. Nævn aldrig VO2 som manglende hvis en Z4/Z5-session er done=True
    3. CTL/TSB/vægt-referencer skal matche de faktiske tal
    4. TSS-compliance må ikke kalde mangler hvis alle planlagte sessions er done
    """
    errors = []

    # Byg sæt af done-labels (lowercase) og done-discs
    done_labels = set()
    done_discs = set()
    all_planned_done = True
    has_vo2_done = False

    for s in (week_sessions or []):
        if s.get('extra'):
            continue  # ignorer ekstra-aktiviteter i QA
        label = (s.get('label') or '').lower()
        disc = s.get('disc', '')
        if s.get('done'):
            done_labels.add(label)
            done_discs.add(disc)
            if any(z in label for z in ['z4', 'z5', 'vo2', 'interval', 'bjerg']):
                has_vo2_done = True
        else:
            all_planned_done = False

    speech_lower = speech.lower()

    # Regel 1+2: Ingen "mangler VO2" hvis VO2 er done
    if has_vo2_done:
        for phrase in ['mangler vo2', 'kør den vo2', 'vo2-session mangler', 'mangler stadig én vo2']:
            if phrase in speech_lower:
                errors.append(f"QA FEJL: Teksten nævner manglende VO2 men en Z4/Z5-session er done=True. Fjern: '{phrase}'")

    # Regel 3: Alle planlagte sessions done — ingen "mangler sessioner"
    if all_planned_done:
        for phrase in ['sessioner står tilbage', 'mangler for at nå', 'ikke gennemført']:
            if phrase in speech_lower:
                errors.append(f"QA FEJL: Alle planlagte sessions er done men teksten antyder mangler. Fjern: '{phrase}'")

    # Regel 4: TSB-referencer skal matche faktiske tal
    if tsb is not None:
        if tsb >= -10 and 'rød zone' in speech_lower:
            errors.append(f"QA FEJL: TSB={tsb} er ikke i rød zone men teksten siger det.")
        if tsb < -30 and 'sundt niveau' in speech_lower:
            errors.append(f"QA FEJL: TSB={tsb} er under -30 (kritisk) men teksten siger 'sundt niveau'.")

    # Regel 5: Vægt-referencer skal matche
    if weight is not None:
        if weight <= weight_goal and 'kalder på fokus på protein' in speech_lower:
            errors.append(f"QA FEJL: Vægt={weight} er under mål ({weight_goal}) men teksten kalder på fokus.")

    if errors:
        print("  ⚠️  Coach QA fejl:")
        for e in errors:
            print(f"    {e}")
    else:
        print("  ✅ Coach QA: ingen fejl")

    return errors


def last_real_within(rows, days=7, today=None):
    """(værdi, dato) for seneste REELLE måling højst `days` dage gammel.

    rows er weightHistory/fatHistory: [{date, v, real}] i kronologisk orden.
    Returnerer (None, None) hvis seneste måling er ældre end vinduet, eller
    hvis der slet ingen målinger er. Bruges som fallback når nattekørslen
    rammer før Garmin har synket dagens vejning.
    """
    from datetime import date as _date, timedelta as _td
    today = today or _date.today()
    cutoff = today - _td(days=days)
    for row in reversed(rows or []):
        if not isinstance(row, dict) or row.get('v') is None:
            continue
        if row.get('real') is False:
            continue
        try:
            d = _date.fromisoformat(str(row.get('date'))[:10])
        except Exception:
            continue
        return (row['v'], str(row['date'])[:10]) if d >= cutoff else (None, None)
    return None, None


def dk_day(iso):
    """'2026-08-05' -> '5/8'. Returnerer None ved ugyldigt input."""
    try:
        _y, _m, _d = str(iso)[:10].split('-')
        return f"{int(_d)}/{int(_m)}"
    except Exception:
        return None


def generate_coach_speech(week_num, weekday, streak, af_this_week, today_session, block_type, week_focus,
                           ctl=None, tsb=None, weight=None, sleep=None, compliance=None,
                           tss_act=None, planned=None, remaining_sessions=None, week_sessions=None,
                           travel_note=None, trajectory_note=None, days_completed=None, weight_goal=None,
                           decoupling_note=None,
                           weight_date=None):
    """Genererer daglig coach-tekst: dagsintro + session + Friel/Martin-vurdering (godt/fokus).

    Coaching-princip: hold Kennet på sporet mod det aktive programs løb (programs.py).
    - Peg ALTID fremad: hvad er næste konkrete handling
    - Nævn ALDRIG manglende sessions der faktisk er done=True
    - Vær direkte og præcis — ikke generisk motivation
    - Brug masterplanen som kontekst — TSS=0 mandag morgen er normalt, ikke et rødt flag
    """
    weight_goal = _goal(weight_goal, 'weightKg', 68)

    # Brug week_sessions (live fra Intervals) som kilden til dagens og resten af ugens plan
    # Dette er altid opdateret og matcher hvad der faktisk er i Intervals.icu
    _all_sessions = [s for s in (week_sessions or []) if not s.get('extra')]
    today_intervals = next((s for s in _all_sessions if s.get('today')), None)
    remaining_intervals = [s for s in _all_sessions if not s.get('done') and not s.get('today')]
    DK_DAYS = ['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag']
    day_name = DK_DAYS[weekday]

    BLOCK_LABELS = {'BUILD':'build-uge','BUILD+':'intensiv build-uge','RECOVERY':'restitutionsuge','TAPER':'taper-uge','RACE':'race-uge'}
    block_label = BLOCK_LABELS.get(block_type, 'træningsuge')

    # Streak-kommentar (fallback highlight)
    if streak >= 14:
        streak_comment = f"{streak} dage i træk — imponerende disciplin."
    elif streak >= 7:
        streak_comment = f"{streak} dage i træk. Hold den streak i live."
    elif streak >= 3:
        streak_comment = f"{streak} AF-dage i træk — godt momentum."
    else:
        streak_comment = f"{af_this_week}/7 AF-dage denne uge. Hvert valg tæller."

    # Tjek faktisk done-status fra week_sessions (ikke remaining_sessions der kan være stale)
    sessions_list = week_sessions or []
    planned_sessions = [s for s in sessions_list if not s.get('extra')]
    done_count = sum(1 for s in planned_sessions if s.get('done'))
    total_planned = len(planned_sessions)
    all_done = (done_count == total_planned) and total_planned > 0
    has_vo2_done = any(
        any(z in (s.get('label') or '').lower() for z in ['z4', 'z5', 'vo2', 'interval', 'bjerg'])
        for s in planned_sessions if s.get('done')
    )

    # Faktisk remaining baseret på week_sessions — ikke stale liste fra main()
    # Split på dato: en session hvis dag er passeret er MISSET — ikke "tilbage"
    _today_iso = date.today().isoformat()
    def _is_past(s):
        d = s.get('date')
        if d:
            return d < _today_iso
        day = s.get('day')
        if day in DAY_SHORT:
            return DAY_SHORT.index(day) < weekday
        return False
    missed_sessions = [s.get('label', '') for s in planned_sessions if not s.get('done') and _is_past(s)]
    actual_remaining = [s.get('label', '') for s in planned_sessions if not s.get('done') and not _is_past(s)]

    # Dagens session
    if today_session and not today_session.get('done'):
        disc = today_session.get('disc','')
        title = today_session.get('label','træning')
        disc_map = {'run':'løb','bike':'cykel','swim':'svøm','strength':'styrke','free':'aktiv restitution'}
        disc_dk = disc_map.get(disc, 'træning')
        session_line = f"I dag: {title} ({disc_dk})."
    elif today_session and today_session.get('done'):
        session_line = "Dagens session er gennemført."
    else:
        session_line = "Hviledag i dag."

    # Ugedag-intro
    if weekday == 0:  # mandag
        intro = f"Ny uge starter — uge {date.today().isocalendar()[1]}. {block_label.capitalize()}."
    elif weekday == 4:  # fredag
        intro = f"Fredag — tre dage tilbage af uge {date.today().isocalendar()[1]}."
    elif weekday == 6:  # søndag
        intro = f"Søndag — afslut uge {date.today().isocalendar()[1]} stærkt."
    else:
        intro = f"{day_name.capitalize()} — uge {date.today().isocalendar()[1]}."

    # --- Friel (træning) + Kreutzer (krop/AF): hvad er godt, hvad skal der fokuseres på ---
    expected_ctl = ctl_plan_for_week(week_num)  # rigtig plan m. recovery-dyk, ikke lineær tilnærmelse
    goods, focus = [], []

    # Dedup 9/7-2026: CTL- og TSB-tal udeladt af teksten — den røde bar (CTL/FORM),
    # CTL-målet i baren og TSB/HRV-advarselsbannerne viser dem allerede.
    # Teksten skal levere vurdering og handling, ikke gentage tal fra UI'et.
    if tsb is not None and tsb < -30:
        focus.append("Formen er under bundgrænsen — prioriter restitution før mere volumen.")

    # Distance-mangel på DAGENS session, selvom den tæller som gennemført/partial
    # (rettet 7/8-2026 — se calc_completion i sessions.py). Et pas med et eksplicit
    # meter-mål (typisk svøm) som lander under 80% af distancen skal nævnes, uanset
    # om TSS/tid alene så pænt ud.
    _distance_focus = build_distance_focus_line(today_intervals)
    if _distance_focus:
        focus.append(_distance_focus)

    # TSS-compliance — kun baseret på faktisk done status
    # Mandag morgen med 0 TSS er NORMALT — der er en fuld uge foran
    is_monday_start = (weekday == 0 and (tss_act or 0) == 0)
    # Blok 9: i RACE/RECOVERY/TAPER er lav TSS meningen — ingen "N procent af
    # ugens TSS" og ingen "X af Y TSS"-linjer, kun én neutral sætning.
    low_load_block = block_type in LOW_LOAD_BLOCKS
    if low_load_block and not is_monday_start:
        goods.append(f"Lavere belastning er meningen i en {block_label} — der er ingen ugeprocent at jagte.")
    elif compliance is not None and not is_monday_start:
        if compliance >= 90 or all_done:
            goods.append(f"{int(compliance)} procent af ugens TSS er i hus.")
        else:
            done_tss = int(tss_act or 0)
            target_tss = int(planned or 0)
            if missed_sessions:
                if len(missed_sessions) == 1:
                    missed_str = f" {missed_sessions[0]} er misset — vinduet er lukket."
                else:
                    missed_str = f" {len(missed_sessions)} sessioner er misset — vinduerne er lukket."
            else:
                missed_str = ""
            if actual_remaining:
                if len(actual_remaining) == 1:
                    rest_str = f"{actual_remaining[0]} står tilbage"
                else:
                    rest_str = f"{len(actual_remaining)} sessioner tilbage, heriblandt {', '.join(actual_remaining[:2])}"
                focus.append(f"{done_tss} af {target_tss} TSS er i hus — {rest_str}.{missed_str}")
            elif missed_sessions:
                focus.append(f"{done_tss} af {target_tss} TSS er i hus.{missed_str}")
            else:
                # actual_remaining er tom = alt er done, selv om compliance < 90 (TSS-afvigelse)
                goods.append(f"Alle sessioner gennemført — {int(compliance)}% af planlagt TSS.")
    elif is_monday_start and today_intervals:
        # Mandag morgen: vis hvad der er planlagt i dag direkte fra Intervals
        label = today_intervals.get('label', 'træning')
        goods.append(f"Fuld uge foran — i dag: {label}.")

    weight_aside = None
    # Vægten kan være seneste måling inden for 7 dage -- ikke nødvendigvis fra i dag.
    # Uden datoen ville en 3 dage gammel vejning blive læst som dagens tal.
    _wsuf = f" (målt {dk_day(weight_date)})" if dk_day(weight_date) else ""
    if weight is not None:
        if weight <= weight_goal:
            goods.append(f"Vægt på {fmt(weight)} kg{_wsuf} er i mål.")
        elif travel_note:
            # Holdes UDENFOR goods[]/focus[] med vilje — begge lister trunkeres til
            # de første par punkter, og denne kontekst skal aldrig kunne drukne.
            # travel_note er her allerede en komplet, retnings-korrekt sætning
            # (bygget af build_weight_context_note) — tilføj ikke mere tekst der
            # kan modsige den faktiske retning.
            weight_aside = f"Vægt på {fmt(weight)} kg{_wsuf} — {travel_note}"
        else:
            focus.append(f"Vægt på {fmt(weight)} kg{_wsuf} — protein ved hvert måltid, alkohol som bevidst valg, "
                         f"søvn 7-8 t. Vægt/fedt vurderes på 7d-snit mod planen, ikke på én vejning.")

    if sleep is not None:
        if sleep >= SLEEP_GOAL_HOURS:
            goods.append(f"Søvn på {fmt(sleep,1)} timer er solid.")
        else:
            focus.append(f"Søvn på {fmt(sleep,1)} timer er under {SLEEP_GOAL_HOURS}-timers målet — prioriter den.")

    # AF-vurdering: relativ til gennemførte dage (weekday 0=man, 1=tirs, osv.)
    # days_completed kommer fra main() og tæller faktisk registrerede AF-dage
    # (inkl. i dag hvis allerede logget) -- IKKE blot kalenderens ugedag.
    if days_completed is None:
        days_completed = weekday  # fallback hvis ikke angivet
    if af_this_week >= AF_GOAL:
        goods.append(f"{af_this_week}/7 AF-dage — ugens mål er ramt.")
    elif weekday == 0 and af_this_week == 0:
        # Mandag morgen: ny uge startet — ingen AF-dage endnu er normalt
        goods.append(f"Ny uge med {streak} dages streak i ryggen. Hold den.")
    elif days_completed > 0 and af_this_week >= days_completed:
        # AF-dage svarer til eller overstiger antallet af afsluttede dage — på rette spor
        remaining_days = 6 - weekday  # dage tilbage inkl. i dag
        needed = max(0, AF_GOAL - af_this_week)
        if needed == 0:
            goods.append(f"{af_this_week} AF-dage hid — mål nået allerede.")
        elif needed <= remaining_days:
            goods.append(f"{af_this_week} AF-dage i {days_completed} gennemførte dage — på rette spor. {needed} mere og ugens mål er i hus.")
        else:
            focus.append(f"{af_this_week} AF-dage hidtil — {needed} mangler i {remaining_days} dage tilbage. Stram op nu.")
    else:
        # Bag kurven relativt til ugedagen
        days_completed_display = max(days_completed, 1)
        remaining_days = 6 - weekday
        needed = max(0, AF_GOAL - af_this_week)
        focus.append(f"{af_this_week} AF-dage i {days_completed_display} afsluttede dage — {needed} mangler i {remaining_days} dage tilbage.")

    if goods:
        highlight = goods[0].rstrip(".")
    else:
        highlight = streak_comment.rstrip(".")

    rest_goods = goods[1:3]
    focus_items = focus[:3]

    parts = []
    if rest_goods:
        parts.append("Godt: " + " ".join(rest_goods))
    if weight_aside:
        parts.append(weight_aside)
    if focus_items:
        parts.append("Fokus: " + " ".join(focus_items))
    elif not rest_goods and not weight_aside:
        parts.append("Alt kører efter planen — bare fortsæt.")

    # Fremadrettet linje: hvad er næste skridt mod målet?
    _wks, _race = weeks_to_next_race()
    if all_done and len(focus) == 0 and _race:
        closing = f"Stærk uge. {int(_wks)} uger til {_race.get('name')} — hold sporet."
    elif all_done and len(focus) == 0:
        closing = "Stærk uge. Hold sporet."
    elif all_done:
        closing = f"Alle sessioner i hus. Juster de små ting, og resten følger."
    elif len(focus) >= 3:
        closing = "Hård uge — men det er sådan formen bygges. Hold ved."
    elif len(focus) == 0:
        closing = "Alt peger den rigtige vej. Hold ilden ved — ikke sluk den."
    else:
        closing = "Keep moving forward."
    parts.append(closing)

    # Aerobt flag på gårsdagens pas. Står FØR store billede: det er dagsaktuelt,
    # og det er den eneste linje der kan ændre hvad Kennet gør i eftermiddag.
    if decoupling_note:
        parts.append(f"❤️ Aerobt: {decoupling_note}")

    # Store billede — kun når trajectory_note er givet (søndage), ikke trunkeret
    if trajectory_note:
        parts.append(f"📊 Store billede: {trajectory_note}")

    # Citat — roterer mellem træning, kost og filosofi efter dag i året
    import datetime as _dt
    day_of_year = _dt.date.today().timetuple().tm_yday
    quote_pools = [QUOTES_TRAINING, QUOTES_DIET, QUOTES_PHILOSOPHY]
    pool = quote_pools[day_of_year % len(quote_pools)]
    quote = pool[day_of_year % len(pool)]
    parts.append("")
    parts.append(quote)

    guide_line = " ".join(parts)
    # Dedup 9/7-2026: session_line udeladt — topbanneret viser allerede dagens pas
    speech = f"{intro} {{HL}} {guide_line}"

    return speech.strip(), highlight.strip()



# Sidste fejl fra AI-kaldet — læses af update_kpi.py og skrives til data.json,
# så en tavs fejl bliver synlig i stedet for at efterlade gammel tekst.
LAST_AI_ERROR = None

# generate_ai_assessment (den 130-linjers f-string-prompt med 20+ prosa-regler)
# er fjernet 6/9-2026 — se generate_coach_v2 nederst + prompts/*.md.


def _redact(msg):
    """data.json er PUBLIC. Fejltekster kan indeholde selve API-nøglen
    (urllib's ValueError citerer hele header-værdien) — strip den ALTID."""
    msg = str(msg)[:300]
    if ANTHROPIC_KEY:
        msg = msg.replace(ANTHROPIC_KEY, '<redacted>')
        msg = msg.replace(ANTHROPIC_KEY.strip(), '<redacted>')
        msg = msg.replace(repr(ANTHROPIC_KEY.encode()), '<redacted>')
        msg = msg.replace(repr(ANTHROPIC_KEY.strip().encode()), '<redacted>')
    return msg


# ═══════════════════════════════════════════════════════════════════════════
# Coach v2 (6/9-2026): kontekst som data (coach_context), regler som fil
# (prompts/*.md), struktureret svar via tool-use, mekanisk validering
# (coach_validate). Erstatter den 130-linjers f-string-prompt ovenfor og det
# separate ugefokus-kald i sessions.py.
# ═══════════════════════════════════════════════════════════════════════════

PROMPTS_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'prompts'))
COACH_MODEL = "claude-sonnet-4-6"
COACH_MAX_TOKENS = 1600
COACH_RETRIES = 2          # antal forsøg i alt ved netværks-/5xx-fejl
VALIDATION_RETRIES = 1     # ekstra kald med fejlen retur til modellen ved valideringsfejl
COACH_TIMEOUT = 45

COACH_TOOL = {
    "name": "coach_output",
    "description": "Dagens coach-vurdering til Kennet som struktureret data. Alle tal skal findes i konteksten.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "oneThing": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Én konkret handling for i dag. Max 140 tegn. Ingen status-resuméer."},
                    "why": {"type": "string", "description": "Begrundelsen i én sætning. Max 160 tegn."},
                },
                "required": ["action", "why"],
            },
            "training": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Træning & load: 1-2 korte sætninger, kun det der kræver opmærksomhed."},
                    "refs": {"type": "array", "items": {"type": "number"}, "description": "Tal brugt i teksten."},
                },
                "required": ["text", "refs"],
            },
            "body": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Krop & kost (7-dages snit mod plan): 1-2 korte sætninger, kun afvigelsen."},
                    "refs": {"type": "array", "items": {"type": "number"}},
                },
                "required": ["text", "refs"],
            },
            "habits": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Vaner: AF, protein, søvn, energi. 1-2 korte sætninger, kun det der halter."},
                    "refs": {"type": "array", "items": {"type": "number"}},
                },
                "required": ["text", "refs"],
            },
            "bigPicture": {"type": "string", "description": "ÉN sætning, max 160 tegn: hvor i programmet, og hvad der betyder mest nu."},
            "weekFocus": {"type": ["string", "null"], "description": "Kun søndag/mandag: ét ugefokus, max 12 ord. Ellers null."},
            "warnings": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "description": "fx spacing, quota, tsb, readiness, cut"},
                        "level": {"type": "string", "enum": ["info", "warn", "act"]},
                        "message": {"type": "string"},
                        "action": {
                            "type": ["object", "null"],
                            "properties": {
                                "label": {"type": "string", "description": "Knaptekst, fx 'Flyt til torsdag'"},
                                "edit": {
                                    "type": "object",
                                    "properties": {
                                        "action": {"type": "string", "enum": ["move", "cancel", "swap_template"]},
                                        "entryId": {"type": "string", "description": "id fra konteksten"},
                                        "date": {"type": "string"},
                                        "toDate": {"type": "string", "description": "ISO-dato ved move"},
                                        "templateId": {"type": "string", "description": "id fra catalog ved swap_template"},
                                    },
                                    "required": ["action", "entryId"],
                                },
                            },
                            "required": ["label", "edit"],
                        },
                    },
                    "required": ["type", "level", "message", "action"],
                },
            },
        },
        "required": ["oneThing", "training", "body", "habits", "bigPicture", "weekFocus", "warnings"],
    },
}


def load_prompt(name, prompts_dir=None):
    """Læs prompts/<name>.md. Fejler højt hvis filen mangler — det er en deploy-fejl."""
    path = os.path.join(prompts_dir or PROMPTS_DIR, f"{name}.md")
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def coach_mode(weekday):
    """'sunday' på søndage (uge-gennemgang + næste uges fokus), ellers 'daily'."""
    return 'sunday' if weekday == 6 else 'daily'


def week_focus_required(weekday):
    return weekday in (6, 0)


def build_messages(ctx, mode=None, prompts_dir=None):
    """(system, user) — prompten som sendes. Konteksten serialiseres som JSON
    uden pynt: tal er tal, ingen dansk formatering."""
    weekday = (ctx.get('today') or {}).get('weekday', 0)
    mode = mode or coach_mode(weekday)
    system = load_prompt('coach_system', prompts_dir)
    tpl = load_prompt('coach_sunday' if mode == 'sunday' else 'coach_daily', prompts_dir)
    ctx_json = json.dumps(ctx, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    if week_focus_required(weekday):
        wf = ("ÉN sætning, max 12 ord, for den uge der starter mandag. Ingen punktum til sidst, ingen emoji."
              if weekday == 0 else "ÉN sætning, max 12 ord, for NÆSTE uge. Ingen punktum til sidst.")
    else:
        wf = "null (ikke søndag/mandag)."
    user = (tpl.replace('{context}', ctx_json)
               .replace('{date}', str((ctx.get('today') or {}).get('date', '')))
               .replace('{weekdayName}', str((ctx.get('today') or {}).get('weekdayName', '')))
               .replace('{weekFocusInstruction}', wf))
    return system, user


def _call_anthropic(system, user, api_key, timeout=COACH_TIMEOUT):
    payload = json.dumps({
        "model": COACH_MODEL,
        "max_tokens": COACH_MAX_TOKENS,
        "system": system,
        "tools": [COACH_TOOL],
        "tool_choice": {"type": "tool", "name": "coach_output"},
        "messages": [{"role": "user", "content": user}],
    }).encode('utf-8')
    req = _urllib_req.Request(
        "https://api.anthropic.com/v1/messages", data=payload, method="POST",
        headers={"Content-Type": "application/json", "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"})
    with _urllib_req.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def parse_tool_result(result):
    """tool_use-blokken fra et Messages-svar -> dict. ValueError hvis den mangler."""
    if result.get("stop_reason") == "max_tokens":
        raise ValueError("trunkeret (stop_reason=max_tokens)")
    for block in result.get("content") or []:
        if block.get("type") == "tool_use" and block.get("name") == COACH_TOOL["name"]:
            inp = block.get("input")
            if isinstance(inp, dict):
                return inp
    raise ValueError("intet tool_use-svar fra modellen")


def _validation_feedback(errors):
    """Tekst der hæftes på brugerbeskeden ved gen-kald efter valideringsfejl."""
    return ("\n\nDIT FORRIGE SVAR BLEV AFVIST AF VALIDERINGEN:\n- " + "\n- ".join(errors)
            + "\nSkriv svaret igen. Brug KUN tal der står ordret i KONTEKST — ingen procent, "
              "omregning eller optælling du selv har lavet. Har du ikke tallet, så udelad det.")


def _rejected_excerpt(raw, errors):
    """Kort uddrag af de afviste felter til data.coach.validationRejected."""
    out = {"errors": errors[:5]}
    for e in errors:
        path = e.split(":")[0].strip()
        key = path.split(".")[0].split("[")[0]
        val = raw.get(key)
        if isinstance(val, dict):
            val = val.get("text") or val.get("action")
        if isinstance(val, str):
            out[path] = val[:200]
    return out


def generate_coach_v2(ctx, api_key=None, mode=None, prompts_dir=None):
    """Kald modellen med konteksten og returnér det VALIDEREDE svar (dict) —
    eller None. Fejl (netværk, trunkering, validering) lander i LAST_AI_ERROR
    (redacted) så update_kpi kan skrive den til data.coach.error/validationError.

    Returnerer (answer, info) hvor info = {'model', 'validationError', 'notes'}.
    """
    global LAST_AI_ERROR
    LAST_AI_ERROR = None
    api_key = api_key if api_key is not None else ANTHROPIC_KEY
    info = {'model': COACH_MODEL, 'validationError': None, 'notes': None}
    if not api_key:
        LAST_AI_ERROR = "ANTHROPIC_API_KEY ikke sat i miljøet"
        print(f"  ⚠️  {LAST_AI_ERROR} — springer coach v2 over")
        return None, info
    from . import coach_validate as _val
    weekday = (ctx.get('today') or {}).get('weekday', 0)
    system, user = build_messages(ctx, mode, prompts_dir)

    def _fetch(user_msg):
        """Ét modelkald med netværks-retry. Returnerer (raw, err)."""
        raw, last_err = None, None
        for attempt in range(1, COACH_RETRIES + 1):
            try:
                raw = parse_tool_result(_call_anthropic(system, user_msg, api_key))
                break
            except Exception as e:  # netværk/5xx/429/format — prøv igen én gang
                body = ""
                try:
                    body = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
                last_err = _redact(f"{type(e).__name__}: {e}" + (f" | body: {body}" if body else ""))
                code = getattr(e, 'code', None)
                retry = attempt < COACH_RETRIES and (code is None or code >= 500 or code == 429)
                print(f"  ⚠️  coach v2 forsøg {attempt} fejlede: {last_err}" + (" — prøver igen" if retry else ""))
                if not retry:
                    break
        return raw, last_err

    def _fix(raw):
        for k in ('oneThing', 'training', 'body', 'habits'):
            if isinstance(raw.get(k), dict):
                for kk, vv in list(raw[k].items()):
                    if isinstance(vv, str):
                        raw[k][kk] = fix_enc(vv)
        for k in ('bigPicture', 'weekFocus'):
            if isinstance(raw.get(k), str):
                raw[k] = fix_enc(raw[k])
        return raw

    # Valideringsfejl (fx et afledt tal som "42 %") kasserede før hele svaret.
    # Nu får modellen fejlen retur og ét gen-kald (VALIDATION_RETRIES) før vi
    # giver op og beholder forrige vurdering.
    user_msg, ok, errors, cleaned = user, False, [], None
    for v_attempt in range(1, VALIDATION_RETRIES + 2):
        raw, last_err = _fetch(user_msg)
        if raw is None:
            LAST_AI_ERROR = last_err or "ukendt fejl"
            return None, info
        raw = _fix(raw)
        ok, errors, cleaned = _val.validate(raw, ctx, require_week_focus=week_focus_required(weekday))
        if ok:
            break
        err_txt = "; ".join(errors)[:400]
        info['validationError'] = err_txt
        info.setdefault('validationRejected', []).append(_rejected_excerpt(raw, errors))
        if v_attempt <= VALIDATION_RETRIES:
            print(f"  ⚠️  coach v2 afvist af validering ({err_txt}) — beder modellen rette")
            user_msg = user + _validation_feedback(errors)
    if not ok:
        LAST_AI_ERROR = "validering: " + info['validationError']
        print(f"  ⚠️  coach v2 kasseret af validering: {info['validationError']}")
        return None, info
    if info.get('validationRejected'):
        print("  ✅ coach v2 rettede sig efter valideringsfeedback")
        info['validationError'] = None
    info['notes'] = cleaned.pop('validationNotes', None)
    print(f"  ✅ coach v2 genereret (oneThing: {cleaned['oneThing']['action'][:60]!r})")
    return cleaned, info


# ── Rendering til de gamle data.json-felter ────────────────────────────────

def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def render_assessment_html(answer, header):
    """coachAssessmentHtml fra de tre sektioner — klasser, ingen inline font-styles."""
    parts = [f'<p class="coach-head"><strong>{_esc(header)}</strong></p>']
    if answer.get('bigPicture'):
        parts.append(f'<p class="coach-sec coach-big">{_esc(answer["bigPicture"])}</p>')
    for key, label in (('training', 'Træning & load'), ('body', 'Krop & kost'), ('habits', 'Vaner')):
        txt = (answer.get(key) or {}).get('text')
        if txt:
            parts.append(f'<p class="coach-sec"><span class="coach-sec-h">{_esc(label)}</span>{_esc(txt)}</p>')
    return ''.join(parts)


def short_text(text, max_chars=220):
    """De første sætninger af en tekst, højst max_chars — til coachSpeech."""
    text = (text or '').strip()
    if len(text) <= max_chars:
        return text
    out = ''
    for sent in re.split(r'(?<=[.!?])\s+', text):
        if len(out) + len(sent) + 1 > max_chars:
            break
        out = (out + ' ' + sent).strip()
    return out or text[:max_chars].rsplit(' ', 1)[0] + '…'


def legacy_fields(answer):
    """coachSpeech/coachHighlight fra v2-svaret. index.html splitter coachSpeech
    på {HL} og lægger coachHighlight imellem."""
    big = (answer.get('bigPicture') or '').strip()
    train = short_text((answer.get('training') or {}).get('text'))
    action = (answer.get('oneThing') or {}).get('action') or ''
    speech = f"{big} {{HL}} {train}".strip()
    return speech, action


def coach_is_stale(prev_hash, ctx_hash, cache_fresh):
    """15/9-2026: 'stale' betyder at en NY vurdering var påkrævet men ikke blev
    lavet — ikke at tallene har rykket sig lidt. Hashen dækker hele konteksten
    (HRV, søvn, CTL-decimaler), så den afviger ved næsten hver kørsel; når
    cachen bevidst holdes (under CACHE_HOURS, ingen ny aktivitet/vejning/AF/
    plan), er den ikke stale. Kun hash-afvigelse + brudt cache (alder eller
    materiel ændring) uden ny vurdering = stale."""
    if not ctx_hash or prev_hash == ctx_hash:
        return False
    return not cache_fresh
