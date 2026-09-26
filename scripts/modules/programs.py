# -*- coding: utf-8 -*-
"""
Programmer — Fast as Fifty.

Et program er en førsteklasses entitet i data/plan.json (top-level `programs`,
id -> program). Det aktive program vælges ud fra dagens dato — ikke ud fra
en fast konfiguration — så systemet aldrig fryser på "sidste uge" når et
program slutter og det næste begynder.

Reglen (samme i plan.html/eva.html's JS):
  1. Programmet hvor start <= i dag <= end for atleten.
  2. Ellers: det seneste program der er startet (frosset visning).
  3. Ellers: det først kommende. Aldrig None hvis der findes mindst ét.

Bagudkompatibilitet: mangler `programs`, syntetiseres de fra de gamle
top-level nøgler `program`/`weeks`/`races`/`goals` (+ `season2027` og
`nextSeason`), så gamle fixtures og tests virker uændret. En atlet med sit
eget `athletes.<a>.program` (Eva) får det som sit primære program.

Intet i dette modul kalder netværk eller læser filer — ren beregning.
"""
from datetime import date, timedelta

LEGACY_ID = "legacy"


# ── Hjælpere ────────────────────────────────────────────────────────────────

def _to_date(d):
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def _end_from(start, total_weeks):
    return (_to_date(start) + timedelta(days=int(total_weeks) * 7 - 1)).isoformat()


def _with_id(pid, prog):
    out = dict(prog)
    out.setdefault("id", pid)
    if "end" not in out and out.get("start") and out.get("totalWeeks"):
        out["end"] = _end_from(out["start"], out["totalWeeks"])
    if "totalWeeks" not in out and out.get("weeks"):
        out["totalWeeks"] = len(out["weeks"])
    return out


def _legacy_programs(plan):
    """Syntetisér programmer fra de gamle top-level nøgler (fixtures/ældre plan.json)."""
    out = {}
    prog = plan.get("program") or {}
    if prog.get("start") and (prog.get("totalWeeks") or plan.get("weeks")):
        meta = plan.get("programMeta") or {}
        pid = (meta.get("activePrograms") or {}).get("kennet") or LEGACY_ID
        athletes = [a for a, v in (plan.get("athletes") or {}).items()
                    if not (isinstance(v, dict) and v.get("program"))] or ["kennet"]
        p = {
            "id": pid,
            "name": prog.get("name", "Program"),
            "athletes": athletes,
            "start": prog["start"],
            "totalWeeks": prog.get("totalWeeks") or len(plan.get("weeks") or []),
            "philosophy": prog.get("philosophy", ""),
            "description": prog.get("description", ""),
            "weeks": list(plan.get("weeks") or []),
            "races": list(plan.get("races") or []),
            "goals": dict(plan.get("goals") or {}),
        }
        out[pid] = _with_id(pid, p)

    s27 = plan.get("season2027") or {}
    if s27.get("weeks"):
        pid = s27.get("targetRace") or "season2027"
        p = {
            "id": pid,
            "name": f"Sæson {s27.get('year', '')}".strip(),
            "athletes": ["kennet"],
            "start": s27["weeks"][0]["start"],
            "totalWeeks": len(s27["weeks"]),
            "philosophy": "durability",
            "description": "",
            "weeks": list(s27["weeks"]),
            "races": list((plan.get("nextSeason") or {}).get("races") or []),
            "goals": {k: v for k, v in (plan.get("goals") or {}).items()
                      if k not in ("swimMeters", "runKmPerWeek")},
            "phases": s27.get("phases", []),
            "weightPlan": s27.get("weightPlan"),
        }
        for k in ("ftpStart", "ftpTarget", "wkgStart", "wkgTarget",
                  "hoursPerWeekAvg", "hoursPerWeekPeak", "ctlPeak", "ctlAtRace"):
            if k in s27:
                p[k] = s27[k]
        out[pid] = _with_id(pid, p)
    return out


def _athlete_programs(plan):
    """Atlet-specifikke programmer (fx athletes.eva.program + athletes.eva.weeks)."""
    out = {}
    for a, v in (plan.get("athletes") or {}).items():
        if not isinstance(v, dict):
            continue
        prog = v.get("program")
        if not (isinstance(prog, dict) and prog.get("start")):
            continue
        pid = prog.get("id") or f"{a}-{prog.get('raceDay', prog['start'])[:4]}"
        races = [r for r in (plan.get("races") or [])
                 if prog.get("raceDay") and r.get("date") == prog.get("raceDay")]
        p = dict(prog)
        p.update({
            "id": pid,
            "athletes": [a],
            "totalWeeks": prog.get("totalWeeks") or len(v.get("weeks") or []),
            "weeks": list(v.get("weeks") or []),
            "races": races,
            "goals": dict(prog.get("goals") or {}),
            "_athleteLevel": True,
        })
        out[pid] = _with_id(pid, p)
    return out


# ── Offentlig API ───────────────────────────────────────────────────────────

def list_programs(plan):
    """Alle programmer (id -> program) inkl. atlet-specifikke og legacy-syntese."""
    plan = plan or {}
    out = {}
    progs = plan.get("programs")
    if isinstance(progs, dict) and progs:
        for pid, p in progs.items():
            out[pid] = _with_id(pid, p)
    else:
        out.update(_legacy_programs(plan))
    out.update(_athlete_programs(plan))
    return out


def programs_for(plan, athlete="kennet"):
    """Programmer for én atlet, sorteret efter startdato."""
    cands = [p for p in list_programs(plan).values()
             if athlete in (p.get("athletes") or [])]
    return sorted(cands, key=lambda p: (_to_date(p["start"]), not p.get("_athleteLevel")))


def active_program(plan, athlete="kennet", today=None):
    """Det aktive program for atleten pr. `today` (default: date.today()).

    start <= today <= end vinder; ellers det seneste program der er startet;
    ellers det først kommende. None kun hvis atleten slet ingen programmer har.
    """
    today = _to_date(today) if today else date.today()
    cands = programs_for(plan, athlete)
    if not cands:
        return None

    def _key(p):
        # Atlet-specifikt program foretrækkes ved ligestilling.
        return (_to_date(p["start"]), bool(p.get("_athleteLevel")))

    current = [p for p in cands
               if _to_date(p["start"]) <= today <= _to_date(p["end"])]
    if current:
        return max(current, key=_key)
    started = [p for p in cands if _to_date(p["start"]) <= today]
    if started:
        return max(started, key=_key)
    return min(cands, key=_key)


def days_total(program):
    return int(program["totalWeeks"]) * 7


def week_no(program, d):
    """1-baseret ugenummer i programmet, clampet til 1..totalWeeks."""
    raw = (_to_date(d) - _to_date(program["start"])).days // 7 + 1
    return min(max(raw, 1), int(program["totalWeeks"]))


def week_no_raw(program, d):
    """Ugenummer UDEN clamp — <1 før start, >totalWeeks efter slut."""
    return (_to_date(d) - _to_date(program["start"])).days // 7 + 1


def in_program(program, d):
    return _to_date(program["start"]) <= _to_date(d) <= _to_date(program["end"])


def program_day(program, d):
    """1-baseret dag i programmet, clampet til 1..days_total."""
    raw = (_to_date(d) - _to_date(program["start"])).days + 1
    return min(max(raw, 1), days_total(program))


def week_start(program, w):
    return _to_date(program["start"]) + timedelta(weeks=int(w) - 1)


def weeks_meta(program):
    return {w["week"]: w for w in (program.get("weeks") or [])}


def week_meta(program, w):
    return weeks_meta(program).get(w, {})


def ctl_plan(program):
    ws = sorted(program.get("weeks") or [], key=lambda w: w["week"])
    return [w.get("ctlTarget") for w in ws]


def block_types(program):
    return {w["week"]: w.get("blockType") for w in (program.get("weeks") or [])}


def next_race(program, today=None):
    """Første race i programmet med dato >= today (+ daysTo). None hvis ingen."""
    today = _to_date(today) if today else date.today()
    races = [r for r in (program.get("races") or []) if r.get("date")]
    races = sorted(races, key=lambda r: r["date"])
    for r in races:
        rd = _to_date(r["date"])
        if rd >= today:
            out = dict(r)
            out["daysTo"] = (rd - today).days
            return out
    return None


def upcoming_races(plan, athlete="kennet", today=None):
    """Kommende løb på tværs af ALLE atletens programmer, sorteret efter dato.
    Dubletter (samme navn+dato i to programmer) fjernes."""
    today = _to_date(today) if today else date.today()
    seen, out = set(), []
    # 26/9-2026: plan.nextSeason.races er også Kennets løb (fx Hegnet Half 7/3-27),
    # selvom de ikke står i programmets egen races-liste.
    extra = ({"id": "nextSeason", "races": (plan.get("nextSeason") or {}).get("races") or []}
             if athlete == "kennet" else None)
    for p in list(programs_for(plan, athlete)) + ([extra] if extra else []):
        for r in (p.get("races") or []):
            if not r.get("date"):
                continue
            key = (r.get("name"), r["date"])
            if key in seen or _to_date(r["date"]) < today:
                continue
            seen.add(key)
            rr = dict(r)
            rr["daysTo"] = (_to_date(r["date"]) - today).days
            rr["programId"] = p.get("id")
            out.append(rr)
    return sorted(out, key=lambda r: r["date"])


def actuals_through_week(plan, athlete, program):
    """athletes.<a>.actualsThroughWeek — men kun hvis det hører til dette program.

    Feltet er skrevet mod ét bestemt program (athletes.<a>.actualsThroughWeekProgram).
    Mangler markøren, antages legacy-adfærd (gælder programmet).
    """
    ath = (plan.get("athletes") or {}).get(athlete) or {}
    val = ath.get("actualsThroughWeek", 0) or 0
    owner = ath.get("actualsThroughWeekProgram")
    if owner and program and owner != program.get("id"):
        return 0
    return val


def describe(program):
    """Kort dansk programbeskrivelse til coach-prompter."""
    races = [r for r in (program.get("races") or []) if r.get("date")]
    race_txt = ", ".join(
        f"{r.get('name')} ({_to_date(r['date']).day}/{_to_date(r['date']).month}, {r.get('priority', '')}-løb)".replace(", -løb)", ")")
        for r in sorted(races, key=lambda r: r["date"]))
    phil = program.get("philosophy") or ""
    txt = f"{program.get('name', 'Program')}: {program.get('totalWeeks')} uger"
    if phil:
        txt += f", filosofi '{phil}'"
    if race_txt:
        txt += f". Mål: {race_txt}"
    return txt
