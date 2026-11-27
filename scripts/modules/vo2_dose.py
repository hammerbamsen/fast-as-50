# -*- coding: utf-8 -*-
"""
VO2-dosis — Fast as Fifty (27/11-2026).

Svarer på ét spørgsmål dashboardet ikke kunne svare på før: fik jeg min
VO2-stimulus, og var den stor nok?

Friel-gaten (modules/friel.py) kender reglen "1 VO2-stimulus pr. build-uge",
men den ser kun PLANEN. Dette modul ser det der faktisk blev kørt, og måler
det i minutter frem for antal pas — fordi 3 × 3 min og 6 × 4 min begge er
"ét VO2-pas", men ikke samme dosis.

Hvorfor minutter i Z5 og ikke Garmins VO2max: VO2max fra uret er ml/kg/min og
stiger mekanisk når vægten falder, uden at motoren er blevet bedre. Det står
allerede i dashboardets eget afsnit "Hvorfor ikke bare VO2max". Dosis er
derimod noget Kennet styrer selv.

Måldosis pr. kalenderuge følger Joe Friels dosering af aerob kapacitet
(Fast After 50, og hans "Aging: Customizing the Base/Build Period"):
  Prep/transition : 3-5 min pr. mikrocyklus
  Tidlig base     : ca. 5 min, fordobles gradvist
  Sen base        : ca. 15 min
  Build/specifik  : 3-4 løbsspecifikke dage, dosis holdes ca. 15 min
  Recovery/taper  : 0 — lette dage skal være lette (kun Z1-2)
Friels 2. udgave (maj 2026) flytter vægten mod mere base og maks. 2 hårde pas
pr. uge. Derfor er målet et LOFT så meget som et gulv: mere er ikke bedre.

Zonekilde pr. disciplin følger projektets regel — cykling måles på watt, løb
og resten på puls. Pace-zoner bruges ikke her, fordi de kræver et API-kald
pr. aktivitet (compute_run_pace_zone_secs), og et 5-ugers vindue ville koste
30+ kald for en marginal forskel.

Rene funktioner. Ingen netværk, ingen fil-I/O.
"""
from datetime import date, timedelta

# Et pas tæller som VO2-stimulus fra og med dette antal minutter i Z5+.
# Under det er det en enkelt indsats op ad en bakke, ikke et interval-pas.
MIN_SESSION_MIN = 4
WEEKS_SHOWN = 4

# Måldosis i minutter Z5+ pr. kalenderuge, pr. fase i season2027.phases.
PHASE_TARGET = {
    "TRANSITION": 4,
    "BASE": 10,          # gennemsnit; ramper 5 -> 15 over fasen, se week_target
    "BUILD": 15,
    "STELVIO": 15,
    "SPECIFIK": 15,
    "PEAK": 4,          # Friels Peak: 3-5 min Z5-fartlek hver tredje dag
    # TAPER staar bevidst ikke her: den er i BLOCK_ZERO og rammer altid mal 0.
}
BASE_RAMP = (5, 15)     # tidlig base -> sen base
# Blocktype slår fasen: en restitutionsuge har ingen dosis, uanset fase.
BLOCK_ZERO = ("RECOVERY", "REST", "TAPER")
# QA 27/11-2026 (fund 4): listen her divergerede fra resten af repoet, saa et
# pas Intervals leverer som "Gravel" eller "MountainBike" faldt tilbage paa puls.
# Pulsen haenger efter ved 2-4 min reps, saa dosis blev underrapporteret 60-80 %.
# Samme liste som sessions.py:197, plan_tab.py:27 og adaptation.py.
BIKE_TYPES = ("Ride", "VirtualRide", "MountainBike", "Cyclocross", "Gravel",
              "GravelRide", "EBikeRide", "MountainBikeRide")


def _z5_secs(act):
    """Sekunder i Z5 og opefter. Cykel på watt, resten på puls.

    Returnerer 0 når zonedata mangler — ikke None, fordi en uge uden
    zonedata i praksis er en uge uden dokumenteret VO2-arbejde.
    """
    if (act.get("type") or "") in BIKE_TYPES:
        pzt = act.get("icu_zone_times") or []
        secs = [z.get("secs", 0) for z in pzt if isinstance(z, dict)]
        if len(secs) > 4:
            # QA 27/11-2026 (fund 5): KUN Z5. Z6/Z7 er anaerobt og
            # neuromuskulaert arbejde, ikke VO2max-arbejde — sprints paa en
            # Z2-tur taalte ellers som VO2-dosis og kunne gore kortet rodt.
            return secs[4] or 0
    hr = act.get("icu_hr_zone_times") or []
    if isinstance(hr, list) and len(hr) > 4:
        # Pulszoner: alt fra Z5 og op, fordi pulsen ikke har et meningsfuldt
        # loft over Z5 paa samme made som watt.
        return sum(z or 0 for z in hr[4:])
    return 0


def _act_date(act):
    raw = act.get("start_date_local") or act.get("start_date") or ""
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def week_target(plan, week_start, block_type=None):
    """Måldosis i minutter for kalenderugen der starter `week_start`.

    Fasen hentes fra season2027.phases via programmets ugenummer. Base ramper
    lineært 5 -> 15 min hen over fasen, så tidlig base ikke måles mod sen
    bases dosis. Returnerer (minutter, fasenavn, blockType) — fasen er altid
    planens fase, aldrig blocktypen, så kortet kan vise begge.
    """
    if block_type and str(block_type).upper().startswith(BLOCK_ZERO):
        return 0, None, block_type
    prog = (plan.get("programs") or {}).get("tds-2027") or {}
    wk = next((w for w in (prog.get("weeks") or [])
               if w.get("start") == week_start.isoformat()), None)
    if wk is None:
        return None, None, None
    bt = str(wk.get("blockType") or "").upper()
    phase = wk.get("phase")
    if bt.startswith(BLOCK_ZERO) or bt == "RACE":
        return 0, phase, wk.get("blockType")
    phases = (plan.get("season2027") or {}).get("phases") or []
    ph = next((p for p in phases if p.get("name") == phase), None)
    if phase == "BASE" and ph:
        lo, hi = ph.get("weekFrom"), ph.get("weekTo")
        w_no = wk.get("week")
        if isinstance(lo, int) and isinstance(hi, int) and hi > lo and isinstance(w_no, int):
            frac = min(1.0, max(0.0, (w_no - lo) / (hi - lo)))
            lo_t, hi_t = BASE_RAMP
            return int(round(lo_t + frac * (hi_t - lo_t))), phase, wk.get("blockType")
    return PHASE_TARGET.get(phase), phase, wk.get("blockType")


def weekly(activities, plan, today=None, weeks=WEEKS_SHOWN):
    """Z5-dosis pr. kalenderuge, ældste først.

    [{isoWeek, start, z5Min, sessions, target, phase, blockType}] — `target`
    kan være None hvis ugen ligger uden for programmet.
    """
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    starts = [this_monday - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]
    buckets = {s: {"secs": 0, "sessions": 0} for s in starts}
    for a in activities or []:
        d = _act_date(a)
        if d is None:
            continue
        monday = d - timedelta(days=d.weekday())
        b = buckets.get(monday)
        if b is None:
            continue
        secs = _z5_secs(a)
        b["secs"] += secs
        if secs >= MIN_SESSION_MIN * 60:
            b["sessions"] += 1
    out = []
    for s in starts:
        target, phase, block_type = week_target(plan, s)
        out.append({
            "isoWeek": s.isocalendar()[1],
            "start": s.isoformat(),
            "z5Min": int(round(buckets[s]["secs"] / 60)),
            "sessions": buckets[s]["sessions"],
            "target": target,
            "phase": phase,
            "blockType": block_type,
        })
    return out


def card(activities, plan, today=None, weeks=WEEKS_SHOWN):
    """data.json-blokken til VO2-dosiskortet.

    Farven sættes her, ikke i UI'et (jf. repoets kontrakt). Den indeværende
    uge er ikke færdig, så den dømmes ikke for lav dosis før lørdag —
    ellers lyste kortet orange hver mandag morgen. For MEGET Z5 flages med
    det samme, fordi skaden allerede er sket:
      grå   = ingen data, eller ugen er i gang (før lørdag) og dosis ikke nået
      grøn  = mindst 80 % af målet (eller 0 min i en restitutionsuge)
      gul   = fra lørdag under 80 %, eller 120-150 %, eller Z5 i en restitutionsuge
      rød   = over 150 % af målet, eller tre FÆRDIGE uger under halv dosis
    """
    rows = weekly(activities, plan, today=today, weeks=weeks)
    today = today or date.today()
    cur = rows[-1] if rows else None
    target = (cur or {}).get("target")
    z5 = (cur or {}).get("z5Min", 0)
    # Den indevaerende uge kan foerst doemmes for LAV dosis sent i ugen: Friels
    # kvalitetspas ligger midt i ugen, saa er der ingen Z5 lordag, er ugen tabt.
    week_late = today.weekday() >= 5
    color, status = "#7F8C8D", "ingen data"

    if cur is not None and target is None and z5:
        # QA 27/11-2026 (fund 6): "ingen data" ved siden af et minuttal er
        # selvmodsigende. Ugen ligger uden for programmet (fx efter 30/8-2027),
        # eller fasen har intet mal — tallet er sandt, dommen findes ikke.
        color, status = "#7F8C8D", "uden for programmet — ingen måldosis"
    elif cur is not None and target is not None:
        # Tre færdige uger under halv dosis — kun uger der er omme, og kun
        # uger med et reelt mål (en restitutionsuge med mål 0 tæller ikke med).
        afsluttede = [r for r in rows[:-1] if r.get("target")]
        under_halv = [r for r in afsluttede if r["z5Min"] < 0.5 * r["target"]]

        if target == 0:
            color, status = ("#27AE60", "restitutionsuge — ingen Z5 planlagt") if z5 <= 2 \
                else ("#F39C12", "restitutionsuge, men der blev kørt Z5")
        elif z5 > 1.5 * target:
            color, status = "#C0392B", "for meget Z5 — Friel: maks ca. 15 min pr. pas"
        elif len(under_halv) >= 3:
            color, status = "#C0392B", "tre uger med under halv dosis"
        elif z5 >= 0.8 * target:
            color, status = ("#F39C12", "over måldosis") if z5 > 1.2 * target \
                else ("#27AE60", "på måldosis")
        elif week_late:
            color, status = "#F39C12", "under måldosis"
        else:
            color, status = "#7F8C8D", f"ugen er i gang — {z5} af {target} min"

    return {
        "weeks": rows,
        "z5Min": z5,
        "target": target,
        "sessions": (cur or {}).get("sessions", 0),
        "phase": (cur or {}).get("phase"),
        "blockType": (cur or {}).get("blockType"),
        "weekLate": week_late,
        "color": color,
        "status": status,
        "minSessionMin": MIN_SESSION_MIN,
    }


def kpi(block):
    """KPI-kortet i I dag/Træning — samme form som de øvrige kpis i data.json."""
    if not block:
        return {"value": "—", "unit": "min", "sub": "VO2-dosis", "color": "#6B7A88"}
    target = block.get("target")
    sess = block.get("sessions") or 0
    if target is None:
        sub = "uden for programmet"
    elif target == 0:
        sub = "restitutionsuge — mål 0"
    else:
        sub = f"mål {target} min · {sess} pas"
    return {"value": str(block.get("z5Min", 0)), "unit": "min", "sub": sub,
            "color": block.get("color") or "#6B7A88"}
