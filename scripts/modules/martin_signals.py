# -*- coding: utf-8 -*-
"""
Martin-signaler — Fast as Fifty (T5).

Opsamler kostrelevante planændringer i data/martin_signals.md, som
integreres i den ugentlige søndagsmail til Martin Kreutzer.
Martin får IKKE løbende notifikationer — filen er intern opsamling.

Relevansfilter (kun ændringer der påvirker energibehov):
  - hårdt pas tilføjet/fjernet/flyttet (VO2, Z4/Z5, interval, tempo, tærskel)
  - langt pas tilføjet/fjernet/flyttet (>= 90 min)
  - samlet daglig varighed ændret >= 45 min

Alt andet (fx flyt af 30 min recovery-spin) er støj og logges ikke.
"""
from datetime import date, datetime, timezone, timedelta

try:
    from . import programs as _programs
except ImportError:  # test_martin_signals.py importerer modulet som top-level
    import programs as _programs

HARD_MARKERS = ("vo2", "z4", "z5", "interval", "tempo", "tærskel", "taerskel",
                "5×3", "4×5", "6×3", "5x3", "4x5", "6x3")
LONG_SECONDS = 90 * 60          # langt pas
DAY_DELTA_SECONDS = 45 * 60     # relevant daglig varighedsændring

MD_HEADER = (
    "# Signaler til Martin — opsamles til søndagsmailen\n"
    "\n"
    "<!-- Auto-opdateret ved plan-redigering. Integreres i den ugentlige\n"
    "     mail til Martin Kreutzer og ryddes derefter. Ingen løbende mails. -->\n"
)


def _secs(wo):
    try:
        return int(wo.get("moving_time") or 0)
    except (TypeError, ValueError):
        return 0


def _is_hard(wo):
    name = (wo.get("name") or "").lower()
    return any(m in name for m in HARD_MARKERS)


def _is_long(wo):
    return _secs(wo) >= LONG_SECONDS


def _tags(wo):
    t = []
    if _is_hard(wo):
        t.append("hårdt")
    if _is_long(wo):
        t.append("langt")
    return t


def _fmt_wo(wo):
    mins = _secs(wo) // 60
    tags = _tags(wo)
    tag_s = f" [{', '.join(tags)}]" if tags else ""
    return f"{wo.get('name', '?')} ({mins} min){tag_s}"


def _day_workouts(plan, d_iso, athlete):
    for d in plan.get("athletes", {}).get(athlete, {}).get("days", []):
        if d.get("date") == d_iso:
            return [e["workout"] for e in d.get("entries", []) if e.get("workout")]
    return []


def _relevant(before, after):
    """Relevant for Martin? Hårdt/langt pas berørt, eller stor varighedsændring."""
    b_names = {(w.get("name"), _secs(w)) for w in before}
    a_names = {(w.get("name"), _secs(w)) for w in after}
    changed = [w for w in before if (w.get("name"), _secs(w)) not in a_names] + \
              [w for w in after if (w.get("name"), _secs(w)) not in b_names]
    if any(_is_hard(w) or _is_long(w) for w in changed):
        return True
    delta = abs(sum(_secs(w) for w in after) - sum(_secs(w) for w in before))
    return delta >= DAY_DELTA_SECONDS


def _week_no(d_iso, plan, athlete="kennet"):
    """Ugenummer i det program der er aktivt på selve datoen (programs.py)."""
    try:
        program = _programs.active_program(plan, athlete, d_iso)
        return _programs.week_no_raw(program, d_iso) if program else None
    except (KeyError, ValueError, TypeError):
        return None


def _dow_da(d_iso):
    days = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
    return days[date.fromisoformat(d_iso).weekday()]


def build_signal(old_plan, new_plan, action, dates_changed, athlete="kennet",
                 now=None):
    """
    Returnerer markdown-blok med kostrelevante ændringer — eller None hvis
    ændringen er irrelevant for Martin. Kun Kennets plan (Martin er Kennets
    kostvejleder).
    """
    if athlete != "kennet":
        return None
    lines = []
    for d_iso in sorted(set(dates_changed or [])):
        before = _day_workouts(old_plan, d_iso, athlete)
        after = _day_workouts(new_plan, d_iso, athlete)
        if not _relevant(before, after):
            continue
        w = _week_no(d_iso, new_plan, athlete)
        b_s = "; ".join(_fmt_wo(x) for x in before) or "hviledag"
        a_s = "; ".join(_fmt_wo(x) for x in after) or "hviledag"
        wk = f"uge {w}, " if w else ""
        lines.append(f"- **{_dow_da(d_iso)} {d_iso}** ({wk}{action}): "
                     f"{b_s} → {a_s}")
    if not lines:
        return None
    ts = (now or datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=2)))).strftime("%d/%m %H:%M")
    return f"\n### Planændring {ts}\n" + "\n".join(lines) + "\n"


def append_signal(existing_md, signal_md):
    """Append signal til eksisterende md-indhold (opretter header hvis tom)."""
    base = existing_md if (existing_md or "").strip() else MD_HEADER
    if not base.endswith("\n"):
        base += "\n"
    return base + signal_md


# ── Ugentlig Martin-mail (blok 8, 8/9-2026) ──────────────────────────────────
#
# build_weekly(data, plan, today) -> {week, isoWeek, lines[8], generatedAt}.
# Ren funktion over data.json + plan.json: alle tal kommer fra data — intet
# gættes, '—' hvor noget mangler. update_kpi.py sætter data.martinMail hver
# kørsel og appender de 8 linjer til data/martin_signals.md om søndagen.

WEEKLY_HEADING = "### Signaler uge"
DOW_SHORT = ("man", "tir", "ons", "tor", "fre", "lør", "søn")
STRENGTH_TYPES = ("WeightTraining", "Workout", "Strength")
LONG_MIN = 90


def _da(v, nd=1):
    """Dansk tal: komma, ægte minus, '—' for None."""
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    s = f"{f:.{nd}f}".replace(".", ",").replace("-", "−")
    return s


def _signed(v, nd=1):
    if v is None:
        return "—"
    f = float(v)
    if round(f, nd) == 0:
        return "0"
    return ("+" if f > 0 else "") + _da(f, nd)


def _win_avg(rows, today, days, min_n=3):
    """Snit af [{date, v}]-punkter med dato i (today−days, today]. None ved < min_n."""
    lo = today - timedelta(days=days - 1)
    vals = []
    for r in (rows or []):
        if not isinstance(r, dict) or r.get("v") is None or not r.get("date"):
            continue
        try:
            d = date.fromisoformat(str(r["date"])[:10])
            v = float(r["v"])
        except (TypeError, ValueError):
            continue
        if lo <= d <= today:
            vals.append(v)
    if len(vals) < min_n:
        return None
    return sum(vals) / len(vals)


def _last7(today):
    return {(today - timedelta(days=i)).isoformat() for i in range(7)}


def _week_tss(data):
    """(faktisk, planlagt) TSS for ugen: data.weekTss, ellers summer fra week_sessions."""
    wt = data.get("weekTss") if isinstance(data.get("weekTss"), dict) else None
    if wt and (wt.get("actual") is not None or wt.get("planned") is not None):
        return wt.get("actual"), wt.get("planned")
    ws = [s for s in (data.get("week_sessions") or []) if isinstance(s, dict)]
    if not ws:
        return None, None
    actual = sum(float(s.get("actual_tss") or 0) for s in ws)
    planned = sum(float(s.get("planned_tss") or 0) for s in ws if not s.get("extra"))
    return actual, (planned or None)


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _prog_week(plan, d, athlete="kennet"):
    """(program, ugenr, week_meta) for datoen d — ({}, None, {}) uden program."""
    try:
        program = _programs.active_program(plan, athlete, d)
        if not program:
            return {}, None, {}
        w = _programs.week_no(program, d)
        return program, w, (_programs.week_meta(program, w) or {})
    except (KeyError, ValueError, TypeError):
        return {}, None, {}


def _line_week(data, plan, today):
    actual, planned = _week_tss(data)
    pct = int(round(actual / planned * 100)) if (actual is not None and planned) else None
    ctl = None
    curve = [v for v in (data.get("ctlCurve") or []) if v is not None]
    if curve:
        ctl = _num(curve[-1])
    if ctl is None:
        ctl = _num(str((data.get("kpis") or {}).get("ctl", {}).get("value", "")).replace(",", "."))
    tsb = _num(data.get("tsb"))
    _p, _w, meta = _prog_week(plan, today)
    return (f"Uge {today.isocalendar()[1]}: TSS {_da(actual, 0)} af {_da(planned, 0)} "
            f"({_da(pct, 0)} %) · CTL {_da(ctl)} (mål {_da(meta.get('ctlTarget'), 0)}) · TSB {_signed(tsb)}")


def _line_body(data):
    body = data.get("body") if isinstance(data.get("body"), dict) else {}
    g, f = body.get("glidepath") or {}, body.get("fat") or {}
    phase, st = g.get("phase"), g.get("status")
    if phase == "cut":
        word = {"plan": "på plan", "foran": "foran", "bagud": "bagud"}.get(st)
        if word and g.get("delta") is not None and st != "plan":
            status = f"{word} {_da(abs(g['delta']))} kg mod glidepath ({_da(g.get('expectedKg'))})"
        elif word:
            status = f"{word} mod glidepath ({_da(g.get('expectedKg'))})"
        else:
            status = g.get("note") or "glidepath: ingen status"
    elif phase == "hold":
        status = f"vedligehold {_da(g.get('targetKg'))} ±{_da(g.get('corridorKg'))}"
    elif phase == "pre":
        status = g.get("note") or (f"cut starter uge {g['cutStartIsoWeek']}" if g.get("cutStartIsoWeek") else "cut starter uge —")
    else:
        status = "intet cut i planen"
    return f"Vægt 7d {_da(g.get('avg7'))} kg · fedt 14d {_da(f.get('avg14'))} % · {status}"


def _line_readiness(data, today):
    hrv7 = _win_avg(data.get("hrvHistory"), today, 7)
    hrv28 = _win_avg(data.get("hrvHistory"), today, 28, min_n=7)
    rhr7 = _win_avg(data.get("rhrHistory"), today, 7)
    sleep7 = _win_avg(data.get("sleepHistory"), today, 7)
    return (f"HRV 7d {_da(hrv7, 0)} (28d {_da(hrv28, 0)}) · hvilepuls {_da(rhr7, 0)} "
            f"· søvn 7d {_da(sleep7)} t")


def _line_habits(data, today):
    days = _last7(today)
    af_log = data.get("af_log") if isinstance(data.get("af_log"), dict) else {}
    af_vals = [v for d, v in af_log.items() if d in days and v is not None]
    af = sum(1 for v in af_vals if int(v) == 0) if af_vals else None
    log = [e for e in (data.get("checkinLog") or []) if isinstance(e, dict) and e.get("date") in days]
    prot = sum(1 for e in log if e.get("protein") == 2) if any(e.get("protein") is not None for e in log) else None
    sult = sum(1 for e in log if e.get("sult") == 2) if any(e.get("sult") is not None for e in log) else None
    return f"AF {_da(af, 0)}/7 · protein 3/3 {_da(prot, 0)}/7 · aftensult {_da(sult, 0)}/7"


def _line_strength(data, plan, today):
    days = _last7(today)
    log = data.get("strengthLog") if isinstance(data.get("strengthLog"), dict) else {}
    sessions = [s for s in (log.get("sessions") or []) if isinstance(s, dict) and s.get("date")]
    if log.get("from"):
        n = sum(1 for s in sessions if s["date"] in days)
    else:
        n = ((data.get("body") or {}).get("strengthWeek") or {}).get("done")
    program, _w, _m = _prog_week(plan, today)
    target = int(((program or {}).get("goals") or {}).get("strengthPerWeek") or 2)
    # Blok 10: 14-dages check-in i stedet for RPE pr. pas.
    ck = ((data.get("strength") or {}).get("checkin") or {}) if isinstance(data.get("strength"), dict) else {}
    last = ck.get("last") if isinstance(ck, dict) else None
    if last and last.get("date"):
        mark = lambda v: "✓" if v else "✗"
        _ld = date.fromisoformat(str(last["date"])[:10])
        ci = f"{_ld.day}/{_ld.month} ben {mark(last.get('legs'))} overkrop {mark(last.get('upper'))}"
    else:
        ci = "—"
    return f"Styrke {_da(n, 0)}/{target} · check-in {ci}"


def _line_cut(data):
    c = ((data.get("body") or {}).get("cutCheck") or {})
    if not c.get("active"):
        return f"Cut-tjek: inaktivt — {c.get('text') or 'intet cut i planen'}"
    return f"Cut-tjek: {c.get('level') or 'ok'} — {c.get('text') or '—'}"


def _load_of(entry, wo, plan_tab_load):
    """'haard' | 'moderat' | 'let' for et plan-entry: plan_tab.load_for_entry
    (samme regel som Plan-fanen) hvis modulet kan importeres, ellers
    data.planTab's load for samme id, ellers HARD_MARKERS på navnet."""
    try:
        try:
            from . import plan_tab as _pt
        except ImportError:
            import plan_tab as _pt
        return _pt.load_for_entry(entry)
    except Exception:
        ld = plan_tab_load.get(entry.get("id"))
        if ld:
            return ld
        return "haard" if _is_hard(wo) else "let"


def _line_next_week(data, plan, today, athlete="kennet"):
    monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
    sunday = monday + timedelta(days=6)
    iso = monday.isocalendar()[1]
    _p, _w, meta = _prog_week(plan, monday, athlete)
    pt_load = {}
    for wk in ((data.get("planTab") or {}).get("sessions") or []):
        for d in wk.get("days", []):
            for e in d.get("entries", []):
                if e.get("id"):
                    pt_load[e["id"]] = e.get("load")
    hard = []
    for d in sorted(plan.get("athletes", {}).get(athlete, {}).get("days", []), key=lambda x: x.get("date", "")):
        d_iso = d.get("date", "")
        if not (monday.isoformat() <= d_iso <= sunday.isoformat()):
            continue
        for e in d.get("entries", []):
            wo = e.get("workout")
            if not wo:
                continue
            mins = _secs(wo) // 60
            if wo.get("type") in STRENGTH_TYPES:
                continue
            if _load_of(e, wo, pt_load) == "haard" or mins >= LONG_MIN:
                dd = date.fromisoformat(d_iso)
                hard.append(f"{DOW_SHORT[dd.weekday()]} {dd.day}/{dd.month} "
                            f"{wo.get('name') or e.get('libraryId') or '?'} {mins} min")
    return (f"Næste uge ({iso}, {meta.get('blockType') or '—'}): TSS-mål {_da(meta.get('tssTarget'), 0)} "
            f"· hårde/lange dage: {', '.join(hard) if hard else 'ingen'}")


def count_plan_changes_since_last_weekly(md):
    """Antal '### Planændring'-afsnit efter seneste '### Signaler uge' (hele filen hvis ingen)."""
    text = md or ""
    idx = text.rfind(WEEKLY_HEADING)
    tail = text[idx:] if idx >= 0 else text
    return tail.count("### Planændring")


def _line_changes(signals_md):
    n = "—" if signals_md is None else str(count_plan_changes_since_last_weekly(signals_md))
    return f"Planændringer siden sidst: {n} — se martin_signals.md"


def build_weekly(data, plan, today=None, signals_md=None):
    """De 8 linjer til Martins søndagsmail — {week, isoWeek, lines, generatedAt}.
    signals_md: indholdet af data/martin_signals.md (None -> linje 8 viser '—')."""
    today = today if isinstance(today, date) else (date.fromisoformat(str(today)[:10]) if today else date.today())
    data = data if isinstance(data, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    _p, week, _m = _prog_week(plan, today)
    lines = [
        _line_week(data, plan, today),
        _line_body(data),
        _line_readiness(data, today),
        _line_habits(data, today),
        _line_strength(data, plan, today),
        _line_cut(data),
        _line_next_week(data, plan, today),
        _line_changes(signals_md),
    ]
    return {"week": week, "isoWeek": today.isocalendar()[1], "lines": lines,
            "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}


def has_weekly(md, iso_week):
    """Har md allerede afsnittet '### Signaler uge {iso}'?"""
    import re
    return re.search(rf"^{re.escape(WEEKLY_HEADING)} {int(iso_week)}\b", md or "", re.M) is not None


def format_weekly(mail):
    """{isoWeek, lines} -> markdown-afsnit til append_signal."""
    return f"\n{WEEKLY_HEADING} {mail['isoWeek']}\n" + "\n".join(f"- {ln}" for ln in mail["lines"]) + "\n"
