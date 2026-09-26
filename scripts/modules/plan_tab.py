# -*- coding: utf-8 -*-
"""
Plan-fanen (blok 4) — data.planTab.

Svarer på "hvor er jeg, hvorfor, og hvad kan jeg flytte?" uden at appen skal
hente plan.json/plan_view.json/bike_library.json selv. Alt regnes her, én
gang, i update_kpi.py — og kan køres offline via build_plan_tab().

Vinduet er aktuel uge −1 .. +7 regnet i KALENDERUGER (mandage). Hver mandag
slås op i det program der er aktivt den dag, så vinduet kan spænde over et
programskifte (fx medoc-2026 uge 14 → tds-2027 uge 1).

Ren beregning — ingen netværk. Biblioteket læses via bike_library.load()
medmindre `lib` gives.
"""
import re
from datetime import date, timedelta

from . import programs as _programs
from . import bike_library as _bike

DAY_SHORT = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"]

TYPE_MAP = {
    'Run': 'run', 'TrailRun': 'run', 'VirtualRun': 'run', 'IndoorRun': 'run',
    'Ride': 'bike', 'VirtualRide': 'bike', 'MountainBike': 'bike',
    'Cyclocross': 'bike', 'Gravel': 'bike', 'GravelRide': 'bike',
    'Swim': 'swim', 'OpenWaterSwim': 'openwater',
    'WeightTraining': 'strength', 'Workout': 'strength', 'Strength': 'strength',
    'Walk': 'walk', 'Hike': 'hike',
}

LONG_MIN = 120          # "langt pas" = nøglepas
MIN_HOURS_HARD = 72     # bike_library.meta.rules.minHoursBetweenHaard (fallback)

_HARD_RE = re.compile(
    r"(\brace\b|\btest\b|vo2|t[æa]rskel|threshold|\bz[45]\b|zone ?[45]|\bhalf\b|marathon|"
    r"\d+\s*[x×]\s*\d+\s*min|\d+\s*[x×]\s*\d+\s*@)", re.I)
_MOD_RE = re.compile(r"(\bz3\b|zone ?3|\bss\b|sweet ?spot|tempo|over-?unders)", re.I)


def _to_date(d):
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def _monday(d):
    d = _to_date(d)
    return d - timedelta(days=d.weekday())


# ── Belastning ──────────────────────────────────────────────────────────────

def load_for_entry(entry, lib=None):
    """Belastning for et plan-entry: bibliotekets `load` for kælderpas, ellers
    heuristik på navn/beskrivelse (Z1/Z2/let/gang = let, Z3/SS/tempo = moderat,
    Z4+/VO2/tærskel/test/race = haard). Styrke er altid let (tæller ikke i
    Friel 5+2 for cykelpas)."""
    wid = entry.get("libraryId")
    if wid:
        try:
            return _bike.load_of(wid, lib)
        except KeyError:
            pass
    wo = entry.get("workout") or {}
    disc = TYPE_MAP.get(wo.get("type") or "", "free")
    if disc == "strength":
        return "let"
    if disc in ("swim", "openwater", "walk", "hike"):
        # Svøm/gang: kun navnet tæller — beskrivelsens "Z3"-drills er ikke en hård dag.
        return load_from_text(wo.get("name", ""), "")
    return load_from_text(wo.get("name", ""), wo.get("description", ""))


def load_from_text(name, description=""):
    """Heuristik for pas uden libraryId. Navnet vejer tungest; beskrivelsen
    bruges kun til at løfte til haard (så 'Løb let 40 + 6 strides' forbliver let)."""
    name = name or ""
    if _HARD_RE.search(name):
        return "haard"
    if _MOD_RE.search(name):
        return "moderat"
    # Z1/Z2/let/gang i navnet -> let uanset beskrivelse
    if re.search(r"(\bz[12]\b|zone ?[12]|\blet\b|\bgang\b|\bwalk\b|\bhike\b|tekni|recovery|easy)", name, re.I):
        return "let"
    head = (description or "")[:200]
    if _HARD_RE.search(head):
        return "haard"
    if _MOD_RE.search(head):
        return "moderat"
    return "let"


# ── Mesocyklus ──────────────────────────────────────────────────────────────

def meso_weeks(weeks):
    """{week: "2/3" | "R"} for et programs weeks-liste.

    Serien er fortløbende uger med SAMME blockType; RECOVERY-uger er "R" og
    bryder serien. (Opgaven sagde "ikke-RECOVERY-uger før næste RECOVERY";
    RACE-ugen 2 ville så tælle med i BASE-serien og give "BASE 2/3" hvor
    programmets purpose siger "Base 1/2". Samme blockType matcher teksten.)
    """
    ws = sorted((w for w in (weeks or []) if w.get("week") is not None), key=lambda w: w["week"])
    out = {}
    runs = []  # [[week, week, ...]]
    for w in ws:
        bt = (w.get("blockType") or "").upper()
        if bt == "RECOVERY":
            out[w["week"]] = "R"
            runs.append(None)
            continue
        if runs and runs[-1] and runs[-1]["bt"] == bt and runs[-1]["weeks"][-1] == w["week"] - 1:
            runs[-1]["weeks"].append(w["week"])
        else:
            runs.append({"bt": bt, "weeks": [w["week"]]})
    for r in runs:
        if not r:
            continue
        n = len(r["weeks"])
        for i, wk in enumerate(r["weeks"], 1):
            out[wk] = f"{i}/{n}"
    return out


# ── Kvote og nøglepas ───────────────────────────────────────────────────────

def quota_used(day_entries, lib=None):
    """Tæl planlagte cykelpas med libraryId pr. belastning."""
    used = {"haard": 0, "moderat": 0}
    for e in day_entries:
        if not e.get("libraryId") or not e.get("workout"):
            continue
        try:
            ld = _bike.load_of(e["libraryId"], lib)
        except KeyError:
            continue
        if ld in used:
            used[ld] += 1
    return used


def key_sessions(entries, limit=2):
    """Op til `limit` navne: hårde pas først, derefter lange (>= 120 min)."""
    hard = [e for e in entries if e.get("load") == "haard" and e.get("name")]
    longs = [e for e in entries if e.get("mins", 0) >= LONG_MIN and e.get("load") != "haard" and e.get("name")]
    names = []
    for e in hard + longs:
        if e["name"] not in names:
            names.append(e["name"])
    return names[:limit]


# ── Hårde pas: afstand ──────────────────────────────────────────────────────

def hard_spacing(sessions, min_hours=MIN_HOURS_HARD):
    """Par af på hinanden følgende hårde pas i vinduet med timer imellem.
    Entries har ingen klokkeslæt, så timer = dage × 24. Alle discipliner tages
    med (Friel: to hårde dage pr. uge, 72 t imellem ved 50+); `disc` følger med
    så klienten kan skelne."""
    hard = []
    for week in sessions:
        for day in week.get("days", []):
            for e in day.get("entries", []):
                if e.get("load") == "haard" and e.get("id") and not e.get("extra"):
                    hard.append((day["date"], e))
    hard.sort(key=lambda t: t[0])
    out = []
    for (d1, a), (d2, b) in zip(hard, hard[1:]):
        hours = (_to_date(d2) - _to_date(d1)).days * 24
        out.append({
            "fromId": a["id"], "fromName": a.get("name"), "fromDate": d1, "fromDisc": a.get("disc"),
            "toId": b["id"], "toName": b.get("name"), "toDate": d2, "toDisc": b.get("disc"),
            "hours": hours, "ok": hours >= min_hours,
        })
    return out


# ── Done/faktisk fra Intervals ──────────────────────────────────────────────

def _match_actuals(day_entries, day_short, remote_sessions, used):
    """Match plan-entries mod sessions fra week_sessions/all_weeks (samme dag +
    disc; navn foretrækkes). `used` er et set af indekser der allerede er brugt."""
    cands = [(i, s) for i, s in enumerate(remote_sessions)
             if s.get("day") == day_short and not s.get("extra") and i not in used]
    for e in day_entries:
        disc = e["disc"]
        pick = None
        for i, s in cands:
            if i in used:
                continue
            sd = s.get("disc")
            same = sd == disc or (sd in ("swim", "openwater") and disc in ("swim", "openwater"))
            if same and (s.get("label") or "") == (e.get("name") or ""):
                pick = (i, s)
                break
        if pick is None:
            for i, s in cands:
                if i in used:
                    continue
                sd = s.get("disc")
                if sd == disc or (sd in ("swim", "openwater") and disc in ("swim", "openwater")):
                    pick = (i, s)
                    break
        if pick is None:
            continue
        i, s = pick
        used.add(i)
        e["done"] = bool(s.get("done"))
        e["actualMins"] = s.get("actual_mins")
        e["actualTss"] = s.get("actual_tss")
        if s.get("completion"):
            e["completion"] = s["completion"]
    # Ekstra aktiviteter (ikke planlagte) på dagen
    extras = []
    for i, s in enumerate(remote_sessions):
        if s.get("day") == day_short and s.get("extra") and i not in used:
            used.add(i)
            extras.append({
                "id": None, "name": s.get("label") or "", "type": None, "disc": s.get("disc", "free"),
                "mins": s.get("actual_mins"), "libraryId": None, "load": "let", "erg": None,
                "purpose": None, "zwiftName": None, "done": True, "actualMins": s.get("actual_mins"),
                "actualTss": s.get("actual_tss"), "note": None, "isKey": False, "extra": True,
            })
    return extras


# ── Hovedfunktion ───────────────────────────────────────────────────────────

def build_plan_tab(plan, plan_view, week_sessions, all_weeks, today, *,
                   lib=None, week_tss_actual=None, ctl_daily=None, travel=None,
                   weeks_back=4, weeks_ahead=None, from_program_start=False, history_weeks=12, chart_weeks_ahead=7, athlete="kennet"):
    """Byg data.planTab. Kan køres offline.

    plan            data/plan.json (dict)
    plan_view       data/plan_view.json (dict) eller None
    week_sessions   data.week_sessions (aktuel uge, med done/actual)
    all_weeks       data.all_weeks {str(uge): {sessions:[...]}} for det AKTIVE program
    today           date/ISO
    lib             bike_library (dict) — default: bike_library.load()
    week_tss_actual data.weekTssActual {str(uge): tss} for det aktive program
    ctl_daily       {iso-dato: ctl} — seneste kendte CTL pr. dag (Intervals wellness)
    travel          liste af {label, start, end} — default plan.travel
    weeks_back      uger bagud (på tværs af programmer), default 4
    weeks_ahead     uger frem; None = til det aktive programs slutning (alle 51 uger for tds-2027)
    chart_weeks_ahead  CTL-grafens vindue frem (ctl.window/targets/phases) — grafen skal ikke
                    strækkes over hele programmet

    `weeks` dækker hele vinduet; `sessions` kun uger der har dage i plan.json (eller
    aktuelle/remote pas) — UI'et slår op på `start`, ikke på indeks. Tomme uger viser
    ugemetadata + "Ingen pas lagt endnu".
    """
    today = _to_date(today)
    lib = lib or _bike.load()
    travel = travel if travel is not None else (plan.get("travel") or [])
    week_tss_actual = week_tss_actual or {}
    ctl_daily = ctl_daily or {}
    all_weeks = all_weeks or {}
    week_sessions = week_sessions or []
    try:
        min_hours = int(_bike.meta(lib)["rules"].get("minHoursBetweenHaard", MIN_HOURS_HARD))
    except Exception:
        min_hours = MIN_HOURS_HARD

    active = _programs.active_program(plan, athlete, today)
    if not active:
        return {"weeks": [], "sessions": [], "ctl": {"history": [], "projection": [], "targets": [], "phases": []},
                "hardSpacing": [], "today": today.isoformat(), "programId": None}

    days_by_date = {}
    for d in (plan.get("athletes") or {}).get(athlete, {}).get("days", []):
        days_by_date[d["date"]] = d

    cur_monday = _monday(today)
    meso_cache = {}

    def _prog_for(monday):
        p = _programs.active_program(plan, athlete, monday)
        if not p or not _programs.in_program(p, monday):
            return None
        return p

    def _meso(p):
        if p["id"] not in meso_cache:
            meso_cache[p["id"]] = meso_weeks(p.get("weeks"))
        return meso_cache[p["id"]]

    def _entry(e, d_iso, race_dates):
        wo = e.get("workout")
        if not wo:
            return None
        wid = e.get("libraryId")
        w = None
        if wid:
            try:
                w = _bike.get(wid, lib)
            except KeyError:
                w = None
        disc = TYPE_MAP.get(wo.get("type") or "", "free")
        mins = int(round((wo.get("moving_time") or 0) / 60))
        load = load_for_entry(e, lib)
        if d_iso in race_dates and disc in ("run", "bike"):
            load = "haard"
        is_key = load == "haard" or mins >= LONG_MIN or d_iso in race_dates
        return {
            "id": e.get("id"), "name": wo.get("name", ""), "type": wo.get("type"), "disc": disc,
            "mins": mins, "libraryId": wid, "load": load,
            "erg": (bool(w.get("erg", True)) if w else None),
            "purpose": (w.get("purpose") if w else None),
            "zwiftName": (w.get("name") if w else None),
            "done": bool(e.get("done")), "actualMins": None, "actualTss": None,
            "note": e.get("note"), "isKey": is_key, "optional": bool(e.get("optional")),
        }

    if from_program_start:
        # 26/9-2026: Plan-fanen viser hele det aktive program (tds-2027 = 51 uger), ikke 4 uger bagud på tværs af programmer.
        weeks_back = max(0, (cur_monday - _monday(_to_date(active["start"]))).days // 7)
        weeks_ahead = max(0, (_monday(_to_date(active["end"])) - cur_monday).days // 7)
    if weeks_ahead is None:
        # Til slutningen af det aktive program — eller af det program der starter i
        # næste uge (6/9: medoc slutter i dag, tds-2027 starter 7/9 => 51 uger frem).
        ends = [_to_date(p["end"]) for p in _programs.programs_for(plan, athlete)
                if _to_date(p["start"]) <= cur_monday + timedelta(weeks=1)]
        last_end = max(ends) if ends else _to_date(active["end"])
        weeks_ahead = max(0, (_monday(last_end) - cur_monday).days // 7)
    weeks_out, sessions_out = [], []
    for off in range(-weeks_back, weeks_ahead + 1):
        monday = cur_monday + timedelta(weeks=off)
        sunday = monday + timedelta(days=6)
        p = _prog_for(monday)
        wk = _programs.week_no(p, monday) if p else None
        meta = _programs.week_meta(p, wk) if p else {}
        same_prog = bool(p and p["id"] == active["id"])
        race_dates = {r["date"] for r in (p.get("races") or []) if r.get("date")} if p else set()

        # Sessions pr. dag
        remote = []
        if same_prog:
            if off == 0 and week_sessions:
                remote = week_sessions
            else:
                remote = (all_weeks.get(str(wk)) or all_weeks.get(wk) or {}).get("sessions", [])
        used = set()
        days = []
        all_entries = []
        for i in range(7):
            d = monday + timedelta(days=i)
            d_iso = d.isoformat()
            raw = days_by_date.get(d_iso, {"date": d_iso, "entries": []})
            entries = [x for x in (_entry(e, d_iso, race_dates) for e in raw.get("entries", [])) if x]
            rest_note = " · ".join(e.get("note") for e in raw.get("entries", []) if not e.get("workout") and e.get("note")) or None
            rest_id = next((e.get("id") for e in raw.get("entries", []) if not e.get("workout") and e.get("id")), None)
            extras = _match_actuals(entries, DAY_SHORT[i], remote, used) if remote else []
            all_entries.extend(entries)
            days.append({"date": d_iso, "weekday": DAY_SHORT[i], "entries": entries + extras,
                         "restNote": rest_note, "restId": rest_id, "isToday": d == today})
        has_days = any(days_by_date.get((monday + timedelta(days=i)).isoformat(), {}).get("entries") for i in range(7))
        if has_days or off == 0 or remote:
            sessions_out.append({"week": wk, "programId": p["id"] if p else None, "start": monday.isoformat(), "days": days})

        # Uge-metadata
        raw_entries = [e for i in range(7) for e in days_by_date.get((monday + timedelta(days=i)).isoformat(), {}).get("entries", [])]
        flags = []
        pv = (plan_view or {}).get(athlete) or {}
        if p and (not pv.get("programId") or pv.get("programId") == p["id"]):
            vw = next((x for x in pv.get("weeks", []) if x.get("week") == wk), None)
            flags = [{"level": f.get("level"), "rule": f.get("rule"), "text": f.get("msg"),
                      "historic": bool(f.get("historic"))} for f in (vw or {}).get("flags", [])]
        races = [{"name": r.get("name"), "date": r["date"], "priority": r.get("priority")}
                 for r in (p.get("races") or []) if r.get("date") and monday.isoformat() <= r["date"] <= sunday.isoformat()] if p else []
        trav = next((t.get("label") for t in travel
                     if t.get("start") and t.get("end") and t["start"] <= sunday.isoformat() and t["end"] >= monday.isoformat()), None)
        tss_actual = None
        if same_prog and monday <= today:
            v = week_tss_actual.get(str(wk))
            tss_actual = v if v is not None else None
        weeks_out.append({
            "week": wk, "programId": p["id"] if p else None, "start": monday.isoformat(), "end": sunday.isoformat(),
            "phase": meta.get("phase"), "blockType": meta.get("blockType"),
            "mesoWeek": _meso(p).get(wk) if p else None,
            "ctlTarget": meta.get("ctlTarget"), "tssTarget": meta.get("tssTarget"), "tssActual": tss_actual,
            "purpose": meta.get("purpose"), "note": meta.get("note"),
            "quota": meta.get("quota") or {"haard": 0, "moderat": 0},
            "quotaUsed": quota_used(raw_entries, lib),
            "keySessions": key_sessions(all_entries),
            "flags": flags, "races": races, "travel": trav,
            "isCurrent": off == 0, "isPast": sunday < today, "hasDays": has_days,
        })

    # CTL: historik 12 uger (på tværs af programmer), projektion, pejlemærker, faser
    history = []
    for k in range(history_weeks - 1, -1, -1):
        monday = cur_monday - timedelta(weeks=k)
        probe = min(monday + timedelta(days=6), today)
        val = None
        for o in range(7):
            cand = (probe - timedelta(days=o)).isoformat()
            if cand in ctl_daily and ctl_daily[cand] is not None:
                val = round(float(ctl_daily[cand]), 1)
                break
        p = _prog_for(monday)
        history.append({"week": _programs.week_no(p, monday) if p else None, "programId": p["id"] if p else None,
                        "start": monday.isoformat(), "ctl": val})
    projection = []
    pv = (plan_view or {}).get(athlete) or {}
    if pv.get("projection") and (not pv.get("programId") or pv.get("programId") == active["id"]):
        end = (cur_monday + timedelta(weeks=chart_weeks_ahead, days=6)).isoformat()
        for pt in pv["projection"]:
            if pt.get("d") and pt["d"] <= end and pt.get("ctl") is not None:
                projection.append({"d": pt["d"], "ctl": round(float(pt["ctl"]), 1)})
    chart_from = (cur_monday - timedelta(weeks=history_weeks - 1)).isoformat()
    chart_to = (cur_monday + timedelta(weeks=chart_weeks_ahead, days=6)).isoformat()
    chart_weeks = [w for w in weeks_out if w["end"] <= chart_to]
    targets = [{"week": w["week"], "start": w["start"], "ctlTarget": w["ctlTarget"]} for w in chart_weeks if w.get("ctlTarget") is not None]
    phases = []
    for w in chart_weeks:
        name = w.get("blockType") or "—"
        if phases and phases[-1]["name"] == name:
            phases[-1]["to"] = w["end"]
        else:
            phases.append({"from": w["start"], "to": w["end"], "name": name})

    return {
        "today": today.isoformat(), "programId": active["id"], "programName": active.get("name"),
        "currentWeek": _programs.week_no(active, today),
        "minHoursHard": min_hours,
        "rules": (lambda r: {"maxHaard": r.get("maxHaardPerWeek"), "maxModerat": r.get("maxModeratPerWeek")})(_bike.meta(lib).get("rules", {})),
        "weeks": weeks_out, "sessions": sessions_out,
        "ctl": {"history": history, "projection": projection, "targets": targets, "phases": phases,
                "window": {"from": chart_from, "to": chart_to}},
        "hardSpacing": hard_spacing(sessions_out, min_hours),
    }
