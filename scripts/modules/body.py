# -*- coding: utf-8 -*-
"""Krop (blok 6, 6/9-2026): svarer på "går cuttet og vanerne den rigtige vej?"

Ren beregning — ingen netværk. Kan køres offline mod plan.json + data.json:

    body = build_body(plan, data, today)          -> data['body']
    weight_kpi(body) / fat_kpi(body)              -> data['kpis']['weight' / 'fat']
    cut_warning(body)                             -> én advarsel (type 'cut') eller None

Nøgler i `body`:
  glidepath   lineær forventet vægt fra weightPlan.startKg (cutStartsFrom) til
              targetKg (targetDate). phase 'pre' | 'cut' | 'hold'. status
              'foran' | 'plan' | 'bagud' | None efter korridor ±0,5 kg OG
              2-mandags-reglen (uden for korridoren to mandage i træk).
  fat         14-dages snit, ændring over 28 d, lineær forventning, status.
  ffm         fedtfri masse = avg14(vægt) × (1 − avg14(fedt)/100). Hold-mål
              (blok 8): baseline = avg14 ved cut-start (i pre: nu), floor =
              baseline − 0,5, status ok/warn mod floor (pre altid ok).
  strength    (blok 8, build_strength) templates fra workout_library, `next`
              (A/B, template, reasoning) og `last4` fra styrke-loggen.
  cutCheck    fem signaler (rate/ffm/strength/recovery/plateau) -> ét level +
              ÉN handlingstekst. Kun aktiv i phase 'cut'. Manglende serier
              vises som 'ingen data' pr. signal — tjekket forsvinder aldrig tavst.
  strengthWeek {done, target} — styrkepas gennemført i ugen (disc=strength, done).

Alle tal er tal (float/int) eller None. Tekster på dansk med kalenderuger (ISO).
Serier har formatet [{date, v, real}|None] som fitness.get_history leverer.
"""
from datetime import date, timedelta
import math

from modules import programs as _programs

CORRIDOR_KG = 0.5        # ±kg omkring glidepath under cut
HOLD_CORRIDOR_KG = 1.0   # ±kg omkring targetKg efter cut
FAT_CORRIDOR_PP = 0.5    # ±procentpoint (bioimpedans-støj)
RATE_WARN = 0.4          # kg/uge tab over 2 uger -> warn
RATE_ACT = 0.6           # kg/uge -> act
FFM_ACT_KG = -0.5        # fedtfri masse over 4 uger -> act
PLATEAU_KG = 0.2         # |Δ 7d-snit| over 3 uger under cut -> info
ALC_WARN_DAYS7 = 3       # drikkedage på 7 dage under cut -> warn
ALC_WARN_RUN = 2         # drikkedage i træk (klynge) under cut -> warn
STRENGTH_TYPES = ('WeightTraining', 'Workout', 'Strength')

COLOR_OK = '#27AE60'
COLOR_WARN = '#E67E22'
COLOR_NEUTRAL = '#7A6A58'

_LEVEL_RANK = {None: 0, 'info': 1, 'warn': 2, 'act': 3}


# ── Hjælpere ────────────────────────────────────────────────────────────────

def _to_date(d):
    if d is None:
        return None
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def _r(v, nd=1):
    if v is None:
        return None
    r = round(float(v), nd)
    return 0.0 if r == 0 else r


def fmt_da(v, nd=1):
    """1 decimal med komma, '—' for None."""
    if v is None:
        return '—'
    return f"{float(v):.{nd}f}".replace('.', ',').replace('-', '−')


def _signed(v, nd=1):
    """+1,2 / −0,8 / 0 — dansk komma, ægte minustegn, aldrig '-0'."""
    if v is None:
        return '—'
    r = round(float(v), nd)
    if r == 0:
        return '0' if nd == 0 else fmt_da(0.0, nd)
    return ('+' if r > 0 else '−') + fmt_da(abs(r), nd)


def _points(series):
    """[{date, v}|None] -> {date: float} (kun punkter med værdi)."""
    out = {}
    for p in (series or []):
        if not isinstance(p, dict) or p.get('v') is None or not p.get('date'):
            continue
        try:
            out[_to_date(p['date'])] = float(p['v'])
        except (TypeError, ValueError):
            continue
    return out


def _last_date(pts):
    return max(pts) if pts else None


def window_avg(series, end, days, min_n=3):
    """Snit af værdier med dato i (end−days, end]. None ved < min_n punkter."""
    pts = series if isinstance(series, dict) else _points(series)
    end = _to_date(end)
    if end is None or not pts:
        return None
    lo = end - timedelta(days=days - 1)
    vals = [v for d, v in pts.items() if lo <= d <= end]
    if len(vals) < min_n:
        return None
    return sum(vals) / len(vals)


def avg_at(series, end, days=7, min_n=3, lookback=6):
    """Som window_avg, men falder tilbage til den seneste dag ≤ end (inden for
    `lookback` dage) hvor der findes et snit — så en dag uden vejning ikke
    giver None midt i en serie."""
    pts = series if isinstance(series, dict) else _points(series)
    end = _to_date(end)
    if end is None or not pts:
        return None
    for back in range(0, lookback + 1):
        v = window_avg(pts, end - timedelta(days=back), days, min_n)
        if v is not None:
            return v
    return None


def iso_week(d):
    return _to_date(d).isocalendar()[1]


def monday_of(d):
    d = _to_date(d)
    return d - timedelta(days=d.weekday())


def dk_short(d):
    d = _to_date(d)
    return f"{d.day}/{d.month}" if d else None


# ── Plan ────────────────────────────────────────────────────────────────────

def find_weight_plan(plan, athlete='kennet', today=None):
    """weightPlan + goals: det aktive programs, ellers det første kommende
    program med et weightPlan (6/9 er medoc-2026 aktivt uden weightPlan, mens
    cuttet ligger i tds-2027 fra 7/9)."""
    today = _to_date(today) if today else date.today()
    active = _programs.active_program(plan, athlete, today)
    goals = dict((active or {}).get('goals') or {})
    if active and active.get('weightPlan'):
        return dict(active['weightPlan']), goals, active
    for p in _programs.programs_for(plan, athlete):
        if p.get('weightPlan') and _to_date(p['end']) >= today:
            return dict(p['weightPlan']), dict(p.get('goals') or goals), p
    return {}, goals, active


def phase_for(wp, today):
    """'pre' | 'cut' | 'hold' | None (intet cut i planen)."""
    today = _to_date(today)
    d0, d1 = _to_date(wp.get('cutStartsFrom')), _to_date(wp.get('targetDate'))
    if not d0 or not d1:
        return None
    if today < d0:
        return 'pre'
    hold_from = None
    hm = wp.get('holdFromMonth')
    if hm:
        try:
            y, m = str(hm)[:7].split('-')
            hold_from = date(int(y), int(m), 1)
        except ValueError:
            hold_from = None
    if today > d1 or (hold_from and today >= hold_from):
        return 'hold'
    return 'cut'


def expected_kg(wp, d):
    """Lineær forventning på dato d. None før cutStartsFrom; targetKg efter targetDate."""
    d = _to_date(d)
    d0, d1 = _to_date(wp.get('cutStartsFrom')), _to_date(wp.get('targetDate'))
    s, t = wp.get('startKg'), wp.get('targetKg')
    if not d0 or not d1 or s is None or t is None or d1 <= d0:
        return None
    if d < d0:
        return None
    if d >= d1:
        return float(t)
    frac = (d - d0).days / float((d1 - d0).days)
    return float(s) - (float(s) - float(t)) * frac


def expected_fat(wp, d):
    d = _to_date(d)
    d0, d1 = _to_date(wp.get('cutStartsFrom')), _to_date(wp.get('targetDate'))
    s, t = wp.get('bodyFatPctStart'), wp.get('bodyFatPctTarget')
    if not d0 or not d1 or s is None or t is None or d1 <= d0 or d < d0:
        return None
    if d >= d1:
        return float(t)
    frac = (d - d0).days / float((d1 - d0).days)
    return float(s) - (float(s) - float(t)) * frac


def expected_for_avg(wp, d, days=7):
    """Forventning der passer til et trailing snit: et 7-dages snit svarer til
    glidepath'en midt i vinduet (d − 3), ellers ligger snittet altid ~0,1 kg
    "bagud" på en faldende linje. Klippes til cutStartsFrom."""
    d = _to_date(d)
    d0 = _to_date(wp.get('cutStartsFrom'))
    mid = d - timedelta(days=days // 2)
    if d0 and mid < d0:
        mid = d0
    return expected_kg(wp, mid)


def expected_fat_for_avg(wp, d, days=14):
    d = _to_date(d)
    d0 = _to_date(wp.get('cutStartsFrom'))
    mid = d - timedelta(days=days // 2)
    if d0 and mid < d0:
        mid = d0
    return expected_fat(wp, mid)


def _corridor_status(delta, corridor):
    if delta is None:
        return None
    if delta < -corridor:
        return 'foran'
    if delta > corridor:
        return 'bagud'
    return 'plan'


# ── Glidepath ───────────────────────────────────────────────────────────────

def glidepath(wp, today, weight_history):
    today = _to_date(today)
    pts = _points(weight_history)
    phase = phase_for(wp, today)
    d0, d1 = _to_date(wp.get('cutStartsFrom')), _to_date(wp.get('targetDate'))
    s, t = wp.get('startKg'), wp.get('targetKg')
    out = {
        'phase': phase, 'cutWeek': None, 'cutWeeks': None, 'isoWeek': iso_week(today),
        'cutStartsFrom': d0.isoformat() if d0 else None, 'targetDate': d1.isoformat() if d1 else None,
        'cutStartIsoWeek': iso_week(d0) if d0 else None, 'startKg': _r(s), 'targetKg': _r(t),
        'expectedKg': None, 'corridorKg': CORRIDOR_KG, 'avg7': None, 'avg7Date': None,
        'delta': None, 'status': None, 'note': None, 'ratePerWeek': None, 'actualRate4w': None,
        'series': [],
    }
    avg7 = avg_at(pts, today, 7)
    out['avg7'] = _r(avg7)
    last = _last_date(pts)
    out['avg7Date'] = last.isoformat() if last else None
    prev28 = avg_at(pts, today - timedelta(days=28), 7)
    if avg7 is not None and prev28 is not None:
        out['actualRate4w'] = _r((avg7 - prev28) / 4.0, 2)

    if not phase:
        return out
    days = (d1 - d0).days
    weeks = days / 7.0
    out['cutWeeks'] = int(math.ceil(weeks))
    if s is not None and t is not None and weeks > 0:
        out['ratePerWeek'] = _r(-(float(s) - float(t)) / weeks, 2)   # negativt = tab
    # Serie til grafen: hver mandag fra cutStartsFrom + slutpunktet
    d = d0
    while d < d1:
        out['series'].append({'date': d.isoformat(), 'expected': _r(expected_kg(wp, d), 2)})
        d += timedelta(days=7)
    out['series'].append({'date': d1.isoformat(), 'expected': _r(expected_kg(wp, d1), 2)})

    if phase == 'pre':
        out['note'] = f"cut starter uge {iso_week(d0)} ({dk_short(d0)})"
        return out

    out['cutWeek'] = min(out['cutWeeks'], (today - d0).days // 7 + 1)
    corridor = HOLD_CORRIDOR_KG if phase == 'hold' else CORRIDOR_KG
    out['corridorKg'] = corridor
    exp = expected_for_avg(wp, today)
    out['expectedKg'] = _r(exp)
    if avg7 is None or exp is None:
        out['note'] = 'ingen vejninger de seneste 7 dage'
        return out
    delta = avg7 - exp
    out['delta'] = _r(delta)
    today_status = _corridor_status(delta, corridor)

    # 2-mandags-reglen: 'foran'/'bagud' kræver samme retning uden for korridoren
    # på de to seneste mandage (inkl. i dag hvis det er mandag).
    m1 = monday_of(today)
    m2 = m1 - timedelta(days=7)
    mondays = []
    for m in (m1, m2):
        if m < d0:
            mondays.append(None)
            continue
        a, e = avg_at(pts, m, 7), expected_for_avg(wp, m)
        mondays.append(_corridor_status(a - e, corridor) if (a is not None and e is not None) else None)
    out['mondays'] = [{'date': m.isoformat(), 'status': st} for m, st in zip((m1, m2), mondays)]
    if today_status == 'plan':
        out['status'] = 'plan'
    elif mondays[0] == today_status and mondays[1] == today_status:
        out['status'] = today_status
    else:
        out['status'] = 'plan'
        out['note'] = (f"{'under' if today_status == 'foran' else 'over'} korridoren — "
                       f"tæller som {today_status} efter to mandage")
    return out


# ── Fedt og fedtfri masse ───────────────────────────────────────────────────

def fat_status(wp, today, fat_history):
    today = _to_date(today)
    pts = _points(fat_history)
    avg14 = avg_at(pts, today, 14, min_n=3, lookback=13)
    prev = avg_at(pts, today - timedelta(days=28), 14, min_n=3, lookback=13)
    phase = phase_for(wp, today)
    exp = expected_fat_for_avg(wp, today) if phase in ('cut', 'hold') else None
    out = {'avg14': _r(avg14), 'avg14Change28d': _r(avg14 - prev) if (avg14 is not None and prev is not None) else None,
           'expected': _r(exp), 'target': _r(wp.get('bodyFatPctTarget')), 'corridorPp': FAT_CORRIDOR_PP,
           'status': None, 'note': '±0,5 pp er måleusikkerhed'}
    if avg14 is not None and exp is not None:
        out['status'] = _corridor_status(avg14 - exp, FAT_CORRIDOR_PP)
    return out


def ffm_status(wp, today, weight_history, fat_history):
    today = _to_date(today)
    wpts, fpts = _points(weight_history), _points(fat_history)

    def _ffm(d):
        w = avg_at(wpts, d, 14, min_n=3, lookback=13)
        f = avg_at(fpts, d, 14, min_n=3, lookback=13)
        if w is None or f is None:
            return None
        return w * (1 - f / 100.0)

    now = _ffm(today)
    prev = _ffm(today - timedelta(days=28))
    t, ft = wp.get('targetKg'), wp.get('bodyFatPctTarget')
    target = float(t) * (1 - float(ft) / 100.0) if (t is not None and ft is not None) else None
    chg = (now - prev) if (now is not None and prev is not None) else None

    # Hold-mål (blok 8): baseline = avg14 ved cut-start, floor = baseline − 0,5.
    # I pre er baseline det nuværende avg14 (cuttet er ikke begyndt) og status
    # altid ok/neutral. target beholdes, men UI'et styrer efter floor.
    phase = phase_for(wp, today)
    d0 = _to_date(wp.get('cutStartsFrom'))
    if phase in ('cut', 'hold') and d0:
        baseline = _ffm(d0)
        baseline_date = d0.isoformat()
    else:
        baseline = now
        baseline_date = today.isoformat() if now is not None else None
    floor = (baseline + FFM_ACT_KG) if baseline is not None else None
    if phase in ('cut', 'hold') and now is not None and floor is not None:
        status = 'ok' if now >= floor - 1e-9 else 'warn'
    elif phase == 'pre':
        status = 'ok' if now is not None else None
    elif chg is not None:
        status = 'warn' if chg < FFM_ACT_KG else 'ok'
    else:
        status = None
    return {'now': _r(now), 'change28d': _r(chg), 'target': _r(target), 'status': status,
            'baseline': _r(baseline), 'baselineDate': baseline_date, 'floor': _r(floor),
            'holdKg': FFM_ACT_KG}


# ── Styrke ──────────────────────────────────────────────────────────────────

def strength_week(week_sessions, goals):
    done = sum(1 for s in (week_sessions or [])
               if isinstance(s, dict) and s.get('disc') == 'strength' and s.get('done'))
    target = int((goals or {}).get('strengthPerWeek') or 2)
    return {'done': done, 'target': target}


def strength_log_from_activities(activities, oldest, newest):
    """Intervals-aktiviteter -> {'from', 'to', 'sessions': [{date, name}]} for
    styrkepas (én pr. dag). from/to siger hvilket vindue loggen dækker."""
    seen, out = set(), []
    for a in (activities or []):
        if not isinstance(a, dict) or a.get('type') not in STRENGTH_TYPES:
            continue
        d = (a.get('start_date_local') or '')[:10]
        if not d or d in seen:
            continue
        seen.add(d)
        out.append({'date': d, 'name': a.get('name') or 'Styrke'})
    return {'from': _to_date(oldest).isoformat(), 'to': _to_date(newest).isoformat(),
            'sessions': sorted(out, key=lambda x: x['date'])}


def merge_strength_log(strength_log, plan_log):
    """Beriger aktivitets-loggen (strength_log_from_activities) med de 3 felter
    fra plan.athletes.kennet.strengthLog {dato: {rpe, complete, note, template,
    at}} matchet på dato. Datoer i plan-loggen uden aktivitet (inden for
    from..to) tilføjes som session med source 'log'. Ren funktion."""
    log = dict(strength_log or {})
    sessions = [dict(s) for s in (log.get('sessions') or []) if isinstance(s, dict) and s.get('date')]
    plog = plan_log if isinstance(plan_log, dict) else {}
    by_date = {s['date']: s for s in sessions}
    lo, hi = log.get('from'), log.get('to')
    for d_iso, rec in sorted(plog.items()):
        if not isinstance(rec, dict):
            continue
        if lo and d_iso < lo or hi and d_iso > hi:
            continue
        s = by_date.get(d_iso)
        if s is None:
            s = {'date': d_iso, 'name': rec.get('template') or 'Styrke (logget)', 'source': 'log'}
            sessions.append(s)
            by_date[d_iso] = s
        s['rpe'] = rec.get('rpe')
        s['complete'] = rec.get('complete')
        s['note'] = rec.get('note') or ''
        s['template'] = rec.get('template')
    for s in sessions:
        s.setdefault('source', 'activity')
        s.setdefault('note', '')
        for k in ('rpe', 'complete', 'template'):
            s.setdefault(k, None)
    log['sessions'] = sorted(sessions, key=lambda x: x['date'])
    return log


def load_workout_library(path=None):
    """data/workout_library.json -> liste af templates ([] ved fejl)."""
    import json as _json
    import os as _os
    p = path or _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', 'data', 'workout_library.json')
    try:
        with open(p, encoding='utf-8') as fh:
            return list(_json.load(fh).get('templates') or [])
    except (OSError, ValueError):
        return []


def strength_templates(templates):
    """Kun styrke-templates med øvelsesliste (blok 8): [{id, name, rounds, exercises, progression}]."""
    out = []
    for t in (templates or []):
        if not isinstance(t, dict) or t.get('type') != 'WeightTraining' or not t.get('exercises'):
            continue
        out.append({'id': t.get('id'), 'name': t.get('name'), 'rounds': t.get('rounds'),
                    'movingTime': t.get('moving_time'),
                    'exercises': [dict(e) for e in t['exercises']], 'progression': t.get('progression')})
    return out


def ab_of(name=None, template_id=None):
    """'a' | 'b' | None ud fra template-id ('-a-'/'-b-', 'styrke-a-') eller navn ('Styrke A …')."""
    tid = (template_id or '').lower()
    for letter in ('a', 'b'):
        if f'-{letter}-' in tid or tid.endswith(f'-{letter}') or tid.startswith(f'styrke-{letter}'):
            return letter
    n = (name or '').strip().lower()
    for letter in ('a', 'b'):
        if n.startswith(f'styrke {letter}') and (len(n) == 8 or not n[8].isalpha()):
            return letter
    return None


def _template_for(letter, rounds, templates):
    """Template med givet bogstav og rundetal — ellers første med bogstavet."""
    cands = [t for t in templates if ab_of(t.get('name'), t.get('id')) == letter]
    for t in cands:
        if t.get('rounds') == rounds:
            return t
    return cands[0] if cands else None


def next_strength(plan, strength_log, today, templates, athlete='kennet', target=2, progression=None):
    """{ab, templateId, name, reasoning, date} — det styrkepas der står i planen
    næste gang (entry med libraryId/templateId eller navn 'Styrke A…'/'Styrke B…'
    fra i dag, ikke gennemført), ellers skiftevis A/B ud fra seneste log.
    Rundetal: 3 fra uge 41 hvis de to seneste afsluttede uger hver har ≥ target
    pas, ellers 2."""
    today = _to_date(today)
    tpls = strength_templates(templates)
    by_id = {t['id']: t for t in tpls}
    weeks = strength_by_week(strength_log, today, weeks=2)
    two_full = len(weeks) == 2 and all(v >= target for v in weeks.values())
    rounds = 3 if (iso_week(today) >= 41 and two_full) else 2

    def _pick(letter, reasoning, d_iso=None, tid=None, recovery=False):
        from . import strength_progression as _sp
        t = by_id.get(tid) or _template_for(letter, rounds, tpls)
        st = _sp.state_for_date(progression, d_iso or today)
        exs = _sp.apply_state(t.get('exercises') if t else [], st)
        return {'ab': letter, 'templateId': t['id'] if t else None,
                'name': t['name'] if t else None, 'rounds': t.get('rounds') if t else rounds,
                'date': d_iso, 'reasoning': reasoning, 'recovery': recovery,
                'exercises': exs, 'state': st, 'stateSummary': _sp.state_summary(st)}

    days = (plan.get('athletes') or {}).get(athlete, {}).get('days', [])
    for d in sorted(days, key=lambda x: x.get('date', '')):
        if d.get('date', '') < today.isoformat():
            continue
        for e in d.get('entries', []):
            if e.get('done'):
                continue
            wo = e.get('workout') or {}
            if wo.get('type') not in STRENGTH_TYPES:
                continue
            tid = e.get('templateId') or e.get('libraryId')
            letter = ab_of(wo.get('name'), tid if tid in by_id else None)
            if not letter:
                continue
            _rec = 'recovery' in f"{e.get('note') or ''} {wo.get('name') or ''}".lower()
            return _pick(letter, f"Planlagt {dk_short(d['date'])}: {wo.get('name')}", d['date'],
                         tid if tid in by_id else None, recovery=_rec)

    last = None
    for s in reversed((strength_log or {}).get('sessions') or []):
        letter = ab_of(s.get('name'), s.get('template'))
        if letter:
            last = (letter, s)
            break
    if last:
        nxt = 'b' if last[0] == 'a' else 'a'
        return _pick(nxt, f"Skiftevis A/B: seneste var {last[0].upper()} ({dk_short(last[1]['date'])})")
    return _pick('a', 'Ingen styrke A/B i plan eller log endnu — start med A')


def strength_last4(strength_log, n=4):
    """De seneste n styrkepas, nyest først: [{date, name, ab, rpe, complete, note}]."""
    out = []
    for s in reversed((strength_log or {}).get('sessions') or []):
        if not isinstance(s, dict) or not s.get('date'):
            continue
        out.append({'date': s['date'], 'name': s.get('name'),
                    'ab': ab_of(s.get('name'), s.get('template')),
                    'rpe': s.get('rpe'), 'complete': s.get('complete'), 'note': s.get('note') or ''})
        if len(out) >= n:
            break
    return out


def strength_frequency(strength_log, today=None, target=2, weeks=8):
    """Frekvens frem for program (28/11-2026, Kennets beslutning).

    Progressionsmotoren regner øvelser, sæt og vægtstigninger ud, som Kennet
    ikke bruger. Det der afgør om man er funktionel som 70-årig, er at passene
    bliver lavet — 2 gange om ugen, resten af livet. Her er tallet:

      {target, thisWeek, weeks: [{start, n, hit}] ældst -> nyest, inkl. denne}

    Den indeværende uge er med og er sjældent færdig; `hit` siger kun om målet
    allerede er nået, ikke om ugen er tabt.
    """
    today = _to_date(today) if today else date.today()
    log = strength_log or {}
    dates = [_to_date(e['date']) for e in (log.get('sessions') or [])
             if isinstance(e, dict) and e.get('date')]
    lo = _to_date(log['from']) if log.get('from') else None
    m_this = monday_of(today)
    out = []
    for k in range(weeks - 1, -1, -1):
        m = m_this - timedelta(days=7 * k)
        # Uger loggen ikke dækker helt er ukendte, ikke nul. Uden dette stod
        # ugen før loggens start som 0 pas (fundet 28/11-2026 mod rigtige data).
        if lo and m < lo:
            continue
        n = sum(1 for d in dates if m <= d <= m + timedelta(days=6))
        out.append({'start': m.isoformat(), 'n': n, 'hit': n >= target})
    this_week = out[-1]['n'] if out and out[-1]['start'] == m_this.isoformat() else 0
    return {'target': int(target), 'thisWeek': this_week, 'weeks': out}


def build_strength(plan, strength_log, today=None, templates=None, athlete='kennet', target=2):
    """data['strength'] = {templates, next, last4, frequency}.

    Kortet viser kun `frequency` (28/11-2026). `next` med progressionen bliver
    beregnet, fordi planen og Word-masteren navngiver passene efter den, men
    vises ikke. Styrke-check-in'et er ude: det spurgte kun for at fodre en
    progression, der ikke laengere staar paa skaermen."""
    today = _to_date(today) if today else date.today()
    tpls = templates if templates is not None else load_workout_library()
    ath = (plan.get('athletes') or {}).get(athlete, {}) if isinstance(plan, dict) else {}
    prog = ath.get('strengthProgression')
    return {'templates': strength_templates(tpls),
            'next': next_strength(plan, strength_log, today, tpls, athlete, target, progression=prog),
            'last4': strength_last4(strength_log),
            'frequency': strength_frequency(strength_log, today, target)}


def strength_by_week(strength_log, today, weeks=4):
    """{mandag (iso-dato): antal styrkepas} for de op til `weeks` afsluttede uger
    før denne uge — KUN uger loggen dækker helt (from ≤ mandag, søndag ≤ to).
    Ældst -> nyest."""
    today = _to_date(today)
    log = strength_log or {}
    if not isinstance(log, dict) or not log.get('from'):
        return {}
    lo, hi = _to_date(log['from']), _to_date(log.get('to') or today)
    dates = [_to_date(e['date']) for e in (log.get('sessions') or []) if isinstance(e, dict) and e.get('date')]
    m_this = monday_of(today)
    out = {}
    for k in range(weeks, 0, -1):
        m = m_this - timedelta(days=7 * k)
        if m < lo or m + timedelta(days=6) > hi:
            continue
        out[m.isoformat()] = sum(1 for d in dates if m <= d <= m + timedelta(days=6))
    return out


def next_strength_day(week_sessions, today):
    """Ugedagsnavn (lille) for næste planlagte, ikke-gennemførte styrkepas i ugen."""
    today = _to_date(today)
    days = ['Man', 'Tir', 'Ons', 'Tor', 'Fre', 'Lør', 'Søn']
    names = ['mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag', 'søndag']
    best = None
    for s in (week_sessions or []):
        if not isinstance(s, dict) or s.get('disc') != 'strength' or s.get('done'):
            continue
        try:
            i = days.index(s.get('day'))
        except ValueError:
            continue
        if i >= today.weekday() and (best is None or i < best):
            best = i
    return names[best] if best is not None else None


# ── Cut-tjek ────────────────────────────────────────────────────────────────

def _sig(level, value, text):
    return {'level': level, 'value': value, 'text': text}


def _no_data(text='ingen data'):
    return {'level': None, 'value': None, 'text': text}


def alcohol_signal(af_log, today):
    """Alkohol under cuttet. af_log = {iso-dato: 0/1} (1 = drikkedag), som
    data.af_log. Tæller registrerede drikkedage de seneste 7 dage (i dag inkl.)
    og længste sammenhængende række; uregistrerede dage bryder rækken.
    warn ved >= ALC_WARN_DAYS7 dage eller en klynge >= ALC_WARN_RUN.
    Klynger rammer HRV hårdere end spredte dage (31/7-2/8 og 4-6/9-2026)."""
    today = _to_date(today)
    if not af_log:
        return _no_data('ingen registrering')
    days, run, best, logged = 0, 0, 0, 0
    for off in range(6, -1, -1):
        v = af_log.get((today - timedelta(days=off)).isoformat())
        if v is None:
            run = 0
            continue
        logged += 1
        if int(v) == 1:
            days += 1
            run += 1
            best = max(best, run)
        else:
            run = 0
    if logged == 0:
        return _no_data('ingen registrering de seneste 7 dage')
    lvl = 'warn' if (days >= ALC_WARN_DAYS7 or best >= ALC_WARN_RUN) else None
    txt = f"{days} drikkedag{'e' if days != 1 else ''} på 7 dage"
    if best >= 2:
        txt += f" · {best} i træk"
    return _sig(lvl, {'days7': days, 'run': best}, txt)


def cut_check(glide, ffm, strength_weeks, strength_target, rhr_history, hrv_history,
              weight_history, today, next_strength=None, af_log=None):
    today = _to_date(today)
    phase = (glide or {}).get('phase')
    if phase != 'cut':
        if phase == 'pre':
            d0 = (glide or {}).get('cutStartsFrom')
            txt = f"Aktiveres uge {iso_week(d0)} ({dk_short(d0)})" if d0 else 'Aktiveres når cuttet starter'
        elif phase == 'hold':
            txt = 'Cut afsluttet — vedligehold'
        else:
            txt = 'Intet cut i planen'
        return {'active': False, 'level': None, 'text': txt, 'signals': {}}

    wpts = _points(weight_history)
    signals = {}

    # rate: 7d-snit faldet > 0,4 kg/uge over 2 uger
    a_now = avg_at(wpts, today, 7)
    a_14 = avg_at(wpts, today - timedelta(days=14), 7)
    if a_now is None or a_14 is None:
        signals['rate'] = _no_data()
    else:
        rate = (a_now - a_14) / 2.0     # kg/uge, negativt = tab
        loss = -rate
        lvl = 'act' if loss > RATE_ACT else ('warn' if loss > RATE_WARN else None)
        signals['rate'] = _sig(lvl, _r(rate, 2), f"{fmt_da(rate, 2)} kg/uge (2 uger)")

    # ffm
    chg = (ffm or {}).get('change28d')
    if chg is None:
        signals['ffm'] = _no_data()
    else:
        signals['ffm'] = _sig('act' if chg < FFM_ACT_KG else None, chg, f"{'+' if chg > 0 else ''}{fmt_da(chg)} kg på 4 uger")

    # strength: < target i to afsluttede uger i træk
    sw = strength_weeks or {}
    keys = sorted(sw)
    if len(keys) < 2:
        signals['strength'] = _no_data('ingen data (kræver to afsluttede uger)')
    else:
        l2 = [sw[k] for k in keys[-2:]]
        lvl = 'warn' if all(v < strength_target for v in l2) else None
        signals['strength'] = _sig(lvl, l2, f"{l2[0]} og {l2[1]} pas de to seneste uger (mål {strength_target})")

    # recovery: RHR +2 og HRV −5 % over 14 dage mens vægt falder
    rpts, hpts = _points(rhr_history), _points(hrv_history)
    r_now, r_prev = window_avg(rpts, today, 14, 4), window_avg(rpts, today - timedelta(days=14), 14, 4)
    h_now, h_prev = window_avg(hpts, today, 14, 4), window_avg(hpts, today - timedelta(days=14), 14, 4)
    if None in (r_now, r_prev, h_now, h_prev) or not h_prev:
        signals['recovery'] = _no_data()
    else:
        rhr_up = r_now - r_prev
        hrv_down = (h_prev - h_now) / h_prev * 100
        losing = a_now is not None and a_14 is not None and a_now < a_14
        lvl = 'warn' if (losing and rhr_up >= 2 and hrv_down >= 5) else None
        signals['recovery'] = _sig(lvl, {'rhr': _r(rhr_up), 'hrvPct': _r(-hrv_down)},
                                   f"hvilepuls {_signed(rhr_up, 0)} · HRV {_signed(-hrv_down, 0)} % (14 dage)")

    # plateau: < 0,2 kg over 3 uger
    a_21 = avg_at(wpts, today - timedelta(days=21), 7)
    if a_now is None or a_21 is None:
        signals['plateau'] = _no_data()
    else:
        d3 = a_now - a_21
        signals['plateau'] = _sig('info' if abs(d3) < PLATEAU_KG else None, _r(d3),
                                  f"{'+' if d3 > 0 else ''}{fmt_da(d3)} kg over 3 uger")

    # alkohol: >= 3 drikkedage /7 eller klynge >= 2 under cut
    signals['alcohol'] = alcohol_signal(af_log, today)

    level = None
    for s in signals.values():
        if _LEVEL_RANK[s['level']] > _LEVEL_RANK[level]:
            level = s['level']

    styrke = f"styrke {next_strength}" if next_strength else 'styrke på plads'
    if signals['ffm']['level'] == 'act':
        text = f"Fedtfri masse {fmt_da(chg)} kg på 4 uger — spis til vedligehold i 3-4 dage, protein 3/3, {styrke}"
    elif signals['rate']['level'] == 'act':
        text = f"Tabet er {fmt_da(-signals['rate']['value'], 2)} kg/uge — spis til vedligehold i 3-4 dage, protein 3/3, {styrke}"
    elif signals['rate']['level'] == 'warn':
        text = f"Tabet er over {fmt_da(RATE_WARN)} kg/uge — læg 200-300 kcal på, protein 3/3"
    elif signals['recovery']['level'] == 'warn':
        text = "Hvilepuls op og HRV ned mens vægten falder — 2-3 dage på vedligehold, søvn først"
    elif signals['alcohol']['level'] == 'warn':
        text = f"{signals['alcohol']['text']} under cuttet — AF resten af ugen før du skærer mere"
    elif signals['strength']['level'] == 'warn':
        text = f"Under {strength_target} styrkepas to uger i træk — book {strength_target} pas i denne uge før du skærer mere"
    elif signals['plateau']['level'] == 'info':
        text = "Plateau — tjek protein-dage og AF før du skærer mere"
    else:
        text = "På plan — fortsæt"
    return {'active': True, 'level': level, 'text': text, 'signals': signals}


# ── Samlet ──────────────────────────────────────────────────────────────────

def build_body(plan, data, today=None, athlete='kennet', strength_log=None):
    """data: dict med weightHistory/fatHistory/rhrHistory/hrvHistory/week_sessions
    (+ evt. strengthLog, af_log). Returnerer data['body']."""
    today = _to_date(today) if today else date.today()
    wp, goals, _prog = find_weight_plan(plan, athlete, today)
    wh, fh = data.get('weightHistory'), data.get('fatHistory')
    g = glidepath(wp, today, wh)
    f = fat_status(wp, today, fh)
    m = ffm_status(wp, today, wh, fh)
    sw = strength_week(data.get('week_sessions'), goals)
    log = strength_log if strength_log is not None else data.get('strengthLog')
    weeks = strength_by_week(log, today)
    check = cut_check(g, m, weeks, sw['target'], data.get('rhrHistory'), data.get('hrvHistory'),
                      wh, today, next_strength=next_strength_day(data.get('week_sessions'), today),
                      af_log=data.get('af_log'))
    return {'asOf': today.isoformat(), 'glidepath': g, 'fat': f, 'ffm': m,
            'strengthWeek': sw, 'strengthWeeks': weeks, 'cutCheck': check}


def _status_color(status):
    if status in ('plan', 'foran'):
        return COLOR_OK
    if status == 'bagud':
        return COLOR_WARN
    return COLOR_NEUTRAL


def status_word(status):
    return {'plan': 'På plan', 'foran': 'Foran', 'bagud': 'Bagud'}.get(status, '')


def weight_kpi(body):
    g = (body or {}).get('glidepath') or {}
    phase, st = g.get('phase'), g.get('status')
    value = fmt_da(g.get('avg7'))
    if phase == 'pre':
        sub = f"cut starter uge {g.get('cutStartIsoWeek')}"
    elif phase == 'hold':
        sub = f"vedligehold {fmt_da(g.get('targetKg'))} ±{fmt_da(g.get('corridorKg'))}"
        if st:
            sub += f" · {status_word(st).lower()}"
    elif phase == 'cut':
        sub = f"forventet {fmt_da(g.get('expectedKg'))}"
        if st == 'plan':
            sub += ' · på plan'
        elif st and g.get('delta') is not None:
            sub += f" · {st} {fmt_da(abs(g['delta']))}"
    else:
        sub = '7d-snit'
    color = _status_color(st) if phase in ('cut', 'hold') else COLOR_NEUTRAL
    if g.get('avg7') is None:
        color = COLOR_NEUTRAL
    return {'value': value, 'unit': 'kg', 'sub': sub, 'color': color}


def fat_kpi(body):
    g = (body or {}).get('glidepath') or {}
    f = (body or {}).get('fat') or {}
    phase, st = g.get('phase'), f.get('status')
    if phase == 'pre':
        sub = f"14d-snit · cut starter uge {g.get('cutStartIsoWeek')}"
    elif phase in ('cut', 'hold') and f.get('expected') is not None:
        sub = f"14d-snit · forventet {fmt_da(f['expected'])}"
    else:
        sub = '14d-snit'
    color = _status_color(st) if (phase in ('cut', 'hold') and f.get('avg14') is not None) else COLOR_NEUTRAL
    return {'value': fmt_da(f.get('avg14')), 'unit': '%', 'sub': sub, 'color': color}


def cut_warning(body):
    """Én regel-advarsel (type 'cut') når cutCheck er warn/act — ellers None.
    Level 'critical' for act (update_kpi's legacy-skala; merge_warnings mapper til act)."""
    c = (body or {}).get('cutCheck') or {}
    if not c.get('active') or c.get('level') not in ('warn', 'act'):
        return None
    return {'type': 'cut', 'level': 'critical' if c['level'] == 'act' else 'warn',
            'message': f"Cut-tjek: {c.get('text')}"}
