"""Coach-tekst, AI-assessment og QA-logik."""
import os, re, json, urllib.request as _urllib_req
from datetime import date, timedelta
from .config import (TOTAL_WEEKS, BASE, AUTH, api_get, fix_enc, fmt, ctl_plan_for_week, ANTHROPIC_KEY,
                      DK_DAYS, DK_MONTHS, DAY_SHORT,
                      CTL_START, CTL_GOAL, AF_GOAL, SLEEP_GOAL_HOURS, SWIM_GOAL_M)

QUOTES_TRAINING = [
    "\"Det er ikke om at have tid. Det er om at tage den.\"",
    "\"Sæt farten ned, så du kan gå langt.\"",
    "\"Konsistens slår intensitet, hver gang.\"",
    "\"Hvil er ikke det modsatte af fremskridt — det er en del af det.\"",
    "\"Formen bygges i kedsomheden — ikke i begejstringen.\"",
    "\"14 uger er lang tid. Men hver dag er kort.\"",
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
            parts.append(f"CTL {fmt(ctl,1)} er {delta} point FORAN ugeplanen (planmål uge {week_num}: {plan_target}).")
        else:
            parts.append(f"CTL {fmt(ctl,1)} er {abs(delta)} point BAG ugeplanen (planmål uge {week_num}: {plan_target}).")

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


def qa_coach_speech(speech, week_sessions, ctl, tsb, weight, af_this_week, tss_act, planned, weight_goal=72):
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


def generate_coach_speech(week_num, weekday, streak, af_this_week, today_session, block_type, week_focus,
                           ctl=None, tsb=None, weight=None, sleep=None, compliance=None,
                           tss_act=None, planned=None, remaining_sessions=None, week_sessions=None,
                           travel_note=None, trajectory_note=None, days_completed=None, weight_goal=72):
    """Genererer daglig coach-tekst: dagsintro + session + Friel/Martin-vurdering (godt/fokus).

    Coaching-princip: hold Kennet på sporet mod Christiansborg (29/8) og Médoc (5/9).
    - Peg ALTID fremad: hvad er næste konkrete handling
    - Nævn ALDRIG manglende sessions der faktisk er done=True
    - Vær direkte og præcis — ikke generisk motivation
    - Brug masterplanen som kontekst — TSS=0 mandag morgen er normalt, ikke et rødt flag
    """

    # Brug week_sessions (live fra Intervals) som kilden til dagens og resten af ugens plan
    # Dette er altid opdateret og matcher hvad der faktisk er i Intervals.icu
    _all_sessions = [s for s in (week_sessions or []) if not s.get('extra')]
    today_intervals = next((s for s in _all_sessions if s.get('today')), None)
    remaining_intervals = [s for s in _all_sessions if not s.get('done') and not s.get('today')]
    DK_DAYS = ['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag']
    day_name = DK_DAYS[weekday]

    BLOCK_LABELS = {'BUILD':'build-uge','BUILD+':'intensiv build-uge','RECOVERY':'restituitionsuge','TAPER':'taper-uge','RACE':'race-uge'}
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
        intro = f"Ny uge starter — uge {week_num} af {TOTAL_WEEKS}. {block_label.capitalize()}."
    elif weekday == 4:  # fredag
        intro = f"Fredag — tre dage tilbage af uge {week_num}."
    elif weekday == 6:  # søndag
        intro = f"Søndag — afslut uge {week_num} stærkt."
    else:
        intro = f"{day_name.capitalize()} — uge {week_num} af {TOTAL_WEEKS}."

    # --- Friel (træning) + Kreutzer (krop/AF): hvad er godt, hvad skal der fokuseres på ---
    expected_ctl = ctl_plan_for_week(week_num)  # rigtig plan m. recovery-dyk, ikke lineær tilnærmelse
    goods, focus = [], []

    # Dedup 9/7-2026: CTL- og TSB-tal udeladt af teksten — den røde bar (CTL/FORM),
    # CTL-målet i baren og TSB/HRV-advarselsbannerne viser dem allerede.
    # Teksten skal levere vurdering og handling, ikke gentage tal fra UI'et.
    if tsb is not None and tsb < -30:
        focus.append("Formen er under bundgrænsen — prioriter restitution før mere volumen.")

    # TSS-compliance — kun baseret på faktisk done status
    # Mandag morgen med 0 TSS er NORMALT — der er en fuld uge foran
    is_monday_start = (weekday == 0 and (tss_act or 0) == 0)
    if compliance is not None and not is_monday_start:
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
    if weight is not None:
        if weight <= weight_goal:
            goods.append(f"Vægt på {fmt(weight)} kg er i mål.")
        elif travel_note:
            # Holdes UDENFOR goods[]/focus[] med vilje — begge lister trunkeres til
            # de første par punkter, og denne kontekst skal aldrig kunne drukne.
            # travel_note er her allerede en komplet, retnings-korrekt sætning
            # (bygget af build_weight_context_note) — tilføj ikke mere tekst der
            # kan modsige den faktiske retning.
            weight_aside = f"Vægt på {fmt(weight)} kg — {travel_note}"
        else:
            focus.append(f"Vægt på {fmt(weight)} kg — hold protein højt og undgå lette kulhydrater om aftenen.")

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
    weeks_to_christiansborg = max(0, round((date(2026, 8, 29) - date.today()).days / 7, 0))
    if all_done and len(focus) == 0:
        closing = f"Stærk uge. {int(weeks_to_christiansborg)} uger til Christiansborg — hold sporet."
    elif all_done:
        closing = f"Alle sessioner i hus. Juster de små ting, og resten følger."
    elif len(focus) >= 3:
        closing = "Hård uge — men det er sådan formen bygges. Hold ved."
    elif len(focus) == 0:
        closing = "Alt peger den rigtige vej. Hold ilden ved — ikke sluk den."
    else:
        closing = "Keep moving forward."
    parts.append(closing)

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


def generate_ai_assessment(week_num, weekday, day_name, ctl, tsb, weight, af_this_week, af_streak,
                             week_sessions, week_focus, today_session, tss_act, planned, travel_note=None,
                             trajectory_note=None, days_completed=None, compliance_summary=None, weight_goal=72):
    """Kalder Anthropic API server-side og returnerer HTML-formateret coach-vurdering."""
    global LAST_AI_ERROR
    LAST_AI_ERROR = None
    if not ANTHROPIC_KEY:
        print("  ⚠️  ANTHROPIC_API_KEY ikke sat — springer AI-vurdering over")
        LAST_AI_ERROR = "ANTHROPIC_API_KEY ikke sat i miljøet"
        return None

    ctl_target = ctl_plan_for_week(week_num)
    kpis_str = (
        f"CTL: {ctl} (uge {week_num}-mål ifølge planen: {ctl_target}), TSB: {tsb}, Vægt: {weight} kg"
        if weight else
        f"CTL: {ctl} (uge {week_num}-mål ifølge planen: {ctl_target}), TSB: {tsb}"
    )
    if days_completed is None:
        days_completed = weekday  # fallback hvis ikke angivet -- afsluttede dage FØR i dag
    af_note = (
        f"AF denne uge: {af_this_week} AF-dage ud af {days_completed} kalenderdage gået (mandag t.o.m. i dag) "
        f"(mål: {AF_GOAL} AF-dage/uge), streak: {af_streak} dage. "
        f"VIGTIGT: I dag ({day_name}) er STADIG I GANG — skriv aldrig at 'dag {days_completed} er afsluttet' "
        f"eller at det er 'dag X af Y' som om ugen er overstået. "
        f"Vurder AF-status RELATIVT til hvor mange dage der er gået i ugen — ikke absolut ift. 7. "
        f"Hvis Kennet har {af_this_week} AF-dage ud af {days_completed} dage gået i ugen, er det {af_this_week}/{max(days_completed,1)}. "
        f"AF-dage handler UDELUKKENDE om alkohol — IKKE om hvilken type træning der er planlagt. "
        f"Skriv ALDRIG at en specifik træningstype 'tæller' eller 'ikke tæller' som AF-dag."
    )
    today_label = today_session.get('label', 'hviledag') if today_session else 'hviledag'
    today_done = today_session.get('done', False) if today_session else False
    today_status = "✅ GENNEMFØRT" if today_done else "⏳ IKKE FORSØGT ENDNU"

    # Grounding: byg eksplicitte lister fra week_sessions, så modellen taler ud fra
    # hvad der FAKTISK er gjort — ikke gætter en årsag til en CTL-afvigelse.
    # Resten splittes i fremtidige (endnu ikke forfaldne) vs missede (dag passeret,
    # ikke done) — præcis som generate_coach_speech gør — så et gennemført eller
    # passeret pas aldrig fejlagtigt lander i "resten af ugen" eller kaldes "manglende".
    def _sess_is_past(s):
        d = s.get('day')
        if d in DAY_SHORT:
            return DAY_SHORT.index(d) < weekday
        return False
    completed = [s for s in week_sessions if s.get('done') and not s.get('today')]
    completed_str = ", ".join(f"{s['day']}: {s['label']}" for s in completed) or "ingen endnu"
    future_remaining = [s for s in week_sessions if not s.get('done') and not s.get('today') and not _sess_is_past(s)]
    missed = [s for s in week_sessions if not s.get('done') and not s.get('today') and _sess_is_past(s)]
    remaining = ", ".join(f"{s['day']}: {s['label']}" for s in future_remaining) or "ingen planlagte"
    missed_str = ", ".join(f"{s['day']}: {s['label']}" for s in missed)
    weight_line = f"\n- Vægt: {weight} kg (seneste måling)" if weight else ""
    compliance_line = (
        f"\n\nZone-compliance denne uge (Friel-analyse):\n{compliance_summary}\n"
        f"VIGTIGT: Vurder BÅDE om workouts er gennemført (tid/TSS) OG om de rigtige zoner er ramt. "
        f"'Steps: X%' = Intervals' compliance-score for workout-steps. "
        f"Zone-% viser faktisk tid i target-zone. Lav zone-% kan skyldes HR-drift (varme), "
        f"terræn, bevidst lavere intensitet, eller at intensiteten faktisk var for lav. "
        f"Løb Z2 med høj HR-Z1 (>95%) og lav pace-Z2 (<30%) i varme er acceptabelt — nævn det som kontekst. "
        f"Cykel Z2 med >50% Z1 og ingen power-struktur tyder på commute, ikke struktureret Z2. "
        f"TERMINOLOGI (altid): for LØB tales der KUN om pace-zone — brug aldrig 'watt' eller 'effekt' om løb. "
        f"For CYKEL tales der KUN om watt-zone/effekt — brug aldrig 'pace' om cykling. Bland aldrig de to. "
        f"RETNING: noten fra compliance-listen siger allerede eksplicit om en afvigelse var for HURTIGT/HÅRDT "
        f"(over target-zonen) eller for ROLIGT/LET (under target-zonen) — brug den retning PRÆCIS som angivet, "
        f"og gæt eller modsig den ALDRIG ud fra HR alene. Lav HR ved en for hurtig pace/watt betyder IKKE at "
        f"intensiteten var for lav — det betyder typisk bare at HR ikke nåede at indhente en for høj pace/watt. "
        f"VERDIKT-PRIORITET: Hver note starter med enten '— on target' eller '— under X%-målet'. Det ER den "
        f"autoritative vurdering. Hvis en note siger 'on target', må din konklusion ALDRIG blive 'for lav effekt' "
        f"eller en instruktion om at 'skrue op/ned' — detaljer der følger efter 'on target' er kun kontekst, "
        f"aldrig en modsigelse af verdikten. Brug KUN korrigerende/kritisk sprog ('for hårdt', 'for lavt', "
        f"'skru op/ned') når noten selv siger 'under X%-målet'. Nævner noten coasting/frihjul eller NP som mere "
        f"retvisende mål, brug DEN vurdering — ikke den rå tid-i-zone-procent alene."
        if compliance_summary else ""
    )
    travel_line = (
        f"\n- VIGTIG KONTEKST om vægt: {travel_note} Brug PRÆCIS denne forklaring/retning i "
        f"'Krop & kost'-linjen i dag — gæt eller modsig den ikke. Bebrejd ALDRIG manglende "
        f"disciplin når denne kontekst er givet."
        if travel_note else ""
    )
    trajectory_line = (
        f"\n- UGENTLIGT STORE BILLEDE (kun søndage): {trajectory_note}"
        if trajectory_note else ""
    )
    fourth_line_instruction = (
        "\n4. 📊 Store billede — brug PRÆCIS tallene fra 'UGENTLIGT STORE BILLEDE' ovenfor "
        "(CTL vs. planmål, vægtudvikling over flere uger). Gæt eller genberegn intet selv."
        if trajectory_note else ""
    )

    prompt = (
        f"Du er Joel Friel-inspireret træningscoach for Kennet Hammerby, 51 år, erfaren Ironman-atlet "
        f"i et 14-ugers reset-år mod to mål: Christiansborg Rundt ({SWIM_GOAL_M}m svøm, 29. aug) og Marathon Médoc (5. sep).\n\n"
        f"Kennet er i uge {week_num} af {TOTAL_WEEKS}, dag {weekday + 1} af 7 ({day_name}). Filosofi: capacity-mode, ikke performance-mode. "
        f"Mål: bygge CTL fra {CTL_START} til {CTL_GOAL} (uge 14), tabe sig til under {weight_goal} kg, {AF_GOAL} AF-dage/uge.\n\n"
        f"Friel-regler:\n- TSB ikke under -30\n- CTL-stigning max 5-8/uge\n"
        f"- Recovery-uge efter hård blok\n- Max 3 løbeture/uge\n\n"
        f"Aktuelle data:\n- {kpis_str}\n- {af_note}\n- Ugefokus: {week_focus[:200]}\n"
        f"- I dag: {today_label} [{today_status}]\n"
        f"- GENNEMFØRT denne uge (fuldførte kendsgerninger): {completed_str}\n"
        + (f"- MISSET denne uge (dag passeret, ikke gennemført): {missed_str}\n" if missed_str else "")
        + f"- Resten af ugen (KUN fremtidige, endnu ikke forfaldne pas): {remaining}{weight_line}{travel_line}{trajectory_line}{compliance_line}\n\n"
        f"VIGTIGT:\n"
        f"- GROUNDING (ufravigelig): Pas i 'GENNEMFØRT denne uge' ER fuldført. Omtal dem ALDRIG som "
        f"manglende, glemt, sprunget over, udestående eller noget der 'skal'/'mangler' at ske. Et pas må "
        f"KUN kaldes manglende/misset hvis det står eksplicit i 'MISSET denne uge'. Hvis CTL ligger under "
        f"ugemålet, forklar det ud fra ugens KARAKTER (fx en let rejse-/restitutionsuge hvor gåture og "
        f"vandringer giver lav TSS) — ALDRIG ved at pege på et pas der står i GENNEMFØRT-listen.\n"
        f"- Hvis dagens session er GENNEMFØRT: Den er en afsluttet kendsgerning. Skriv UDELUKKENDE i DATID om den. "
        f"Skriv ALDRIG sætninger der fremstiller den som noget der 'starter', 'skal' eller 'mangler' at ske — "
        f"fx 'det starter med dagens cykeltur' eller 'hold wattene oppe i dagens tur' er FORBUDT sprog for en "
        f"gennemført session. Ethvert forbedringspunkt fra dagens session skal formuleres som læring til NÆSTE "
        f"lignende session (nævn evt. hvilken kommende dag) — aldrig som en handling for 'i dag'.\n"
        f"- Hvis IKKE gennemført: her ER 'i dag'/'dagens'-sprog korrekt — giv konkrete, fremadrettede råd.\n"
        f"- Nævn KUN vægt hvis aktuel måling.\n\n"
        f"SPROG: Skriv klart, naturligt dansk som en rigtig træner ville tale. Hver sætning skal kunne "
        f"forstås i første gennemlæsning. Undgå tvetydige eller kluntede formuleringer — fx aldrig "
        f"'frem for' når du mener 'i løbet af' eller 'de næste'. Brug korte, konkrete sætninger. "
        f"Ingen kancellisprog.\n\n"
        f"Giv en KORT coach-vurdering (max 4 sætninger pr. linje) opdelt i linjer med emoji-header:\n"
        f"1. 💪 Træning & load (CTL={ctl}, TSB={tsb})\n"
        f"2. ⚖️ Krop & kost\n"
        f"3. 🎯 AF-status & fokus for resten af ugen"
        f"{fourth_line_instruction}\n\n"
        f"Skriv direkte til Kennet på dansk. Vær præcis — ingen tom ros.\n"
        f"Start IKKE med en header-linje som 'Dag X af Y uger' — den tilføjes automatisk."
    )

    try:
        payload = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 800,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()

        req = _urllib_req.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01"
            }
        )
        with _urllib_req.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            if result.get("stop_reason") == "max_tokens":
                print("  ⚠️  AI-vurdering trunkeret (max_tokens) — kasseres, beholder forrige")
                LAST_AI_ERROR = "trunkeret (stop_reason=max_tokens)"
                return None
            text = fix_enc(result["content"][0]["text"])
            print(f"  ✅ AI-vurdering genereret ({len(text)} tegn)")
            return text
    except Exception as e:
        _body = ""
        try:
            _body = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        LAST_AI_ERROR = _redact(f"{type(e).__name__}: {e}" + (f" | body: {_body}" if _body else ""))
        print(f"  ⚠️  AI-vurdering fejlede: {LAST_AI_ERROR}")
        return None

