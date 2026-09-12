# -*- coding: utf-8 -*-
"""
Coach v2 — konteksten som DATA.

build_context() samler alt coachen må vide i ét JSON-serialiserbart dict:
program, dagens pas, ugen (gennemført/misset/tilbage), fitness, readiness,
krop (inkl. cut mod weightPlan), vaner, næste løb, flags og regler.

Alle tal er tal (int/float). Dansk formatering (komma, enheder) sker først når
noget renderes — aldrig her. Ingen netværk: alt kommer fra plan.json og det
data-dict update_kpi.py allerede har bygget (data.json + friske målinger).

Konteksten er også det eneste modellen må citere tal fra — coach_validate.py
tjekker svaret mekanisk mod netop dette dict.
"""
import hashlib
import json
from datetime import date, timedelta

from . import programs as _programs
from . import plan_tab as _plan_tab
from . import bike_library as _bike
from . import friel as _friel

DAY_SHORT = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"]
DK_DAYS = ['mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag', 'søndag']

SLEEP_H_MAX = 8            # "7-8 t" i Fast as Fifty-principperne
HRV_BASELINE_DAYS = 42


# ── Små hjælpere ────────────────────────────────────────────────────────────

def _to_date(d):
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def _num(v, nd=1):
    """float afrundet, eller None. Aldrig en streng."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    r = round(f, nd)
    return 0.0 if r == 0 else r


def _compact(d):
    """Fjern None-felter fra en række — kortere prompt, samme indhold."""
    return {k: v for k, v in d.items() if v is not None}


def _int(v):
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _series_vals(rows, last=None):
    """[{date,v,real}|None] -> [float] (kun punkter med værdi), evt. de sidste `last`."""
    vals = [float(r['v']) for r in (rows or []) if isinstance(r, dict) and r.get('v') is not None]
    return vals[-last:] if last else vals


def _avg(vals, nd=1, min_n=1):
    vals = [v for v in (vals or []) if v is not None]
    if len(vals) < min_n:
        return None
    return round(sum(vals) / len(vals), nd)


def _sd(vals, nd=1, min_n=5):
    vals = [v for v in (vals or []) if v is not None]
    if len(vals) < min_n:
        return None
    m = sum(vals) / len(vals)
    return round((sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5, nd)


def _last_val(rows):
    for r in reversed(rows or []):
        if isinstance(r, dict) and r.get('v') is not None:
            return float(r['v'])
    return None


def _last_avg(series):
    for v in reversed(series or []):
        if v is not None:
            return float(v)
    return None


def _avg_at(series, back):
    """Værdi i en glidende-snit-serie `back` pladser før den seneste værdi."""
    idx = [i for i, v in enumerate(series or []) if v is not None]
    if not idx:
        return None
    i = idx[-1] - back
    if i < 0 or (series[i] is None):
        return None
    return float(series[i])


# ── Delkontekster ───────────────────────────────────────────────────────────

def _program_ctx(plan, program, today, athlete, lib):
    if not program:
        return None
    wk = _programs.week_no(program, today)
    meta = _programs.week_meta(program, wk)
    meso = _plan_tab.meso_weeks(program.get('weeks')).get(wk)
    monday = today - timedelta(days=today.weekday())
    days_by_date = {d['date']: d for d in (plan.get('athletes') or {}).get(athlete, {}).get('days', [])}
    raw_entries = [e for i in range(7)
                   for e in days_by_date.get((monday + timedelta(days=i)).isoformat(), {}).get('entries', [])]
    return {
        'id': program.get('id'), 'name': program.get('name'),
        'philosophy': program.get('philosophy'),
        'phase': meta.get('phase'), 'blockType': meta.get('blockType'),
        'week': wk, 'totalWeeks': _int(program.get('totalWeeks')),
        'weekStart': monday.isoformat(),
        'purpose': meta.get('purpose'), 'note': meta.get('note'),
        'ctlTarget': _num(meta.get('ctlTarget')), 'tssTarget': _num(meta.get('tssTarget'), 0),
        'quota': dict(meta.get('quota') or {'haard': 0, 'moderat': 0}),
        'quotaUsed': _plan_tab.quota_used(raw_entries, lib),
        'mesoWeek': meso,
    }


def _entry_from_plan_tab(e):
    return _compact({
        'id': e.get('id'), 'name': e.get('zwiftName') or e.get('name'), 'disc': e.get('disc'),
        'mins': _int(e.get('mins')), 'load': e.get('load'), 'erg': e.get('erg'),
        'libraryId': e.get('libraryId'), 'purpose': e.get('purpose'), 'isKey': bool(e.get('isKey')),
        'done': bool(e.get('done')), 'actualMins': _int(e.get('actualMins')),
        'actualTss': _int(e.get('actualTss')), 'extra': bool(e.get('extra')),
    })


def _entry_from_week_session(s):
    dist = s.get('actual_distance_m')
    return _compact({
        'id': None, 'name': s.get('label'), 'disc': s.get('disc'),
        'mins': _int(s.get('planned_mins')), 'load': None, 'erg': None,
        'libraryId': None, 'purpose': None, 'isKey': False,
        'done': bool(s.get('done')), 'actualMins': _int(s.get('actual_mins')),
        'actualTss': _int(s.get('actual_tss')), 'extra': bool(s.get('extra')),
        'actualKm': _num(dist / 1000.0) if dist else None,
    })


def _today_ctx(today, week_sessions, plan_tab):
    iso = today.isoformat()
    sessions = None
    if plan_tab and plan_tab.get('sessions'):
        for wk in plan_tab['sessions']:
            for day in wk.get('days', []):
                if day.get('date') == iso:
                    sessions = [_entry_from_plan_tab(e) for e in day.get('entries', [])]
                    break
            if sessions is not None:
                break
    if sessions is None:
        sessions = [_entry_from_week_session(s) for s in (week_sessions or []) if s.get('today')]
    # Faktiske tal fra week_sessions (planTab har dem kun når de er matchet)
    ws_today = [s for s in (week_sessions or []) if s.get('today') and not s.get('extra')]
    for e in sessions:
        if e.get('actualMins') is None:
            m = next((s for s in ws_today if (s.get('label') or '') == (e.get('name') or '')
                      or s.get('disc') == e.get('disc')), None)
            if m:
                e['done'] = bool(m.get('done')) or bool(e.get('done'))
                e['actualMins'] = _int(m.get('actual_mins'))
                e['actualTss'] = _int(m.get('actual_tss'))
                if m.get('actual_distance_m'):
                    e['actualKm'] = _num(m['actual_distance_m'] / 1000.0)
    return {
        'date': iso, 'weekday': today.weekday(), 'weekdayName': DK_DAYS[today.weekday()],
        'sessions': sessions,
    }


def _week_ctx(today, week_sessions, plan_tab, planned_tss, tss_actual):
    """Samme grounding som coach.py's GENNEMFØRT/MISSET/RESTEN — som data."""
    wd = today.weekday()

    def _past(s):
        d = s.get('day')
        return d in DAY_SHORT and DAY_SHORT.index(d) < wd

    def _row(s):
        r = _entry_from_week_session(s)
        r.pop('extra', None)            # listen siger det allerede
        if not r.get('isKey'):
            r.pop('isKey', None)
        r['day'] = s.get('day')
        r['plannedTss'] = _int(s.get('planned_tss'))
        return _compact(r)

    planned = [s for s in (week_sessions or []) if not s.get('extra')]
    completed = [_row(s) for s in planned if s.get('done') and not s.get('today')]
    missed = [_row(s) for s in planned if not s.get('done') and not s.get('today') and _past(s)]
    remaining = [_row(s) for s in planned if not s.get('done') and not s.get('today') and not _past(s)]
    extras = [_row(s) for s in (week_sessions or []) if s.get('extra')]

    # Entry-id'er på de kommende pas (fra planTab) — så advarsler kan pege på dem
    upcoming = []
    hard_spacing = []
    if plan_tab:
        horizon = (today + timedelta(days=14)).isoformat()
        for wk in plan_tab.get('sessions', []):
            for day in wk.get('days', []):
                if today.isoformat() <= day.get('date', '') <= horizon:
                    for e in day.get('entries', []):
                        if e.get('id') and not e.get('extra'):
                            upcoming.append(_compact({'id': e['id'], 'date': day['date'], 'name': e.get('zwiftName') or e.get('name'),
                                                      'disc': e.get('disc'), 'load': e.get('load'), 'mins': _int(e.get('mins')),
                                                      'libraryId': e.get('libraryId'), 'done': bool(e.get('done'))}))
        lo = (today - timedelta(days=7)).isoformat()
        for p in plan_tab.get('hardSpacing', []):
            if lo <= p.get('toDate', '') <= horizon:
                hard_spacing.append({'fromId': p.get('fromId'), 'fromName': p.get('fromName'), 'fromDate': p.get('fromDate'),
                                     'toId': p.get('toId'), 'toName': p.get('toName'), 'toDate': p.get('toDate'),
                                     'hours': _int(p.get('hours')), 'ok': bool(p.get('ok'))})
        # id'er på ugens tilbageværende pas
        for r in remaining:
            if r.get('day') in DAY_SHORT:
                d_iso = (today - timedelta(days=wd) + timedelta(days=DAY_SHORT.index(r['day']))).isoformat()
                m = next((u for u in upcoming if u['date'] == d_iso and (u['name'] == r['name'] or u['disc'] == r['disc'])), None)
                if m:
                    r['id'] = m['id']

    tss_a = _int(tss_actual)
    tss_p = _int(planned_tss)
    return {
        'completed': completed, 'missed': missed, 'remaining': remaining, 'extras': extras,
        'counts': {'completed': len(completed), 'missed': len(missed), 'remaining': len(remaining)},
        'tssPlanned': tss_p, 'tssActual': tss_a,
        'tssPct': _int(tss_a / tss_p * 100) if (tss_a is not None and tss_p) else None,
        'upcoming': upcoming, 'hardSpacing': hard_spacing,
    }


def _fitness_ctx(data, ctl, atl, tsb, ctl_target, plan_tab):
    curve = [v for v in (data.get('ctlCurve') or []) if v is not None]
    ramp = None
    hist = ((plan_tab or {}).get('ctl') or {}).get('history') or []
    hv = [h.get('ctl') for h in hist if h.get('ctl') is not None]
    if len(hv) >= 2:
        ramp = round(float(hv[-1]) - float(hv[-2]), 1)
    elif len(curve) >= 2:
        ramp = round(float(curve[-1]) - float(curve[-2]), 1)
    ef = data.get('efTrend') or {}
    ef_out = {k: {'pct': _num(v.get('pct')), 'n': _int(v.get('n'))}
              for k, v in ef.items() if isinstance(v, dict) and v.get('pct') is not None}
    flag = data.get('aerobicFlag')
    flag_out = None
    if isinstance(flag, dict) and flag.get('flagged'):
        flag_out = {'date': flag.get('date'), 'discipline': flag.get('discipline'), 'name': flag.get('name'),
                    'pct': _num(flag.get('pct')), 'level': flag.get('level'),
                    'warm': bool(flag.get('warm')), 'tempC': _num(flag.get('temp_c'))}
    if ctl is None and curve:
        ctl = curve[-1]
    if tsb is None:
        tsb = data.get('tsb')
    return {
        'ctl': _num(ctl), 'atl': _num(atl), 'tsb': _num(tsb), 'ctlTarget': _num(ctl_target),
        'ctlVsTarget': _num(float(ctl) - float(ctl_target)) if (ctl is not None and ctl_target is not None) else None,
        'rampRate': ramp, 'efTrend': ef_out or None, 'aerobicFlag': flag_out,
    }


def _readiness_ctx(data, wellness):
    w = wellness or {}
    hrv_rows = data.get('hrvHistory') or []
    sleep_rows = data.get('sleepHistory') or []
    rhr_rows = data.get('rhrHistory') or []
    hrv = _num(w.get('hrv')) if w.get('hrv') is not None else _num(_last_val(hrv_rows))
    hrv7 = _num(w.get('hrv_avg')) if w.get('hrv_avg') is not None else _avg(_series_vals(hrv_rows, 7))
    hrv42_vals = _series_vals(hrv_rows, HRV_BASELINE_DAYS)
    sleep_last = _num(_last_val(sleep_rows))
    sleep7 = _avg(_series_vals(sleep_rows, 7))
    if sleep7 is None and w.get('sleep_avg') is not None:
        sleep7 = _num(w.get('sleep_avg'))
    rhr = _int(w.get('rhr')) if w.get('rhr') is not None else _int(_last_val(rhr_rows))
    rhr7 = _num(w.get('rhr_avg')) if w.get('rhr_avg') is not None else _avg(_series_vals(rhr_rows, 7))
    hrv_pct = None
    if hrv is not None and hrv7:
        hrv_pct = _int((hrv - hrv7) / hrv7 * 100)
    return {
        'hrv': hrv, 'hrvAvg7': hrv7, 'hrvVsAvg7Pct': hrv_pct,
        'hrvAvg42': _avg(hrv42_vals, min_n=5), 'hrvSd42': _sd(hrv42_vals),
        'band': _friel.readiness_band(hrv, hrv7, sleep_last),
        'sleepLast': sleep_last, 'sleepAvg7': sleep7,
        'rhr': rhr, 'rhrAvg7': rhr7,
    }


def cut_status(weight_plan, today, weight_avg7):
    """Cut-status mod programmets weightPlan. active KUN når cutStartsFrom er sat
    og passeret. expectedKg er lineær fra startKg til targetKg over
    cutStartsFrom..targetDate."""
    wp = weight_plan or {}
    start = wp.get('cutStartsFrom')
    out = {'active': False, 'startsFrom': start, 'weekOf': None, 'expectedKg': None,
           'deltaVsPlan': None, 'ratePerWeek': None, 'startKg': _num(wp.get('startKg')),
           'targetKg': _num(wp.get('targetKg')), 'targetDate': wp.get('targetDate')}
    if not start:
        return _compact(out)
    try:
        d0 = _to_date(start)
        d1 = _to_date(wp.get('targetDate')) if wp.get('targetDate') else None
    except ValueError:
        return out
    start_kg, target_kg = wp.get('startKg'), wp.get('targetKg')
    if d1 and d1 > d0 and start_kg is not None and target_kg is not None:
        weeks = (d1 - d0).days / 7.0
        out['ratePerWeek'] = round((float(start_kg) - float(target_kg)) / weeks, 2)
    if today < d0:
        out['daysToStart'] = (d0 - today).days
        return _compact(out)
    if d1 and today > d1:
        out['ended'] = True
        return _compact(out)  # cut er slut (vedligehold) — ikke aktivt
    out['active'] = True
    out['weekOf'] = (today - d0).days // 7 + 1
    if d1 and start_kg is not None and target_kg is not None:
        frac = min(1.0, (today - d0).days / float((d1 - d0).days))
        exp = float(start_kg) - (float(start_kg) - float(target_kg)) * frac
        out['expectedKg'] = round(exp, 1)
        if weight_avg7 is not None:
            out['deltaVsPlan'] = round(float(weight_avg7) - exp, 1)
    return out


def _body_ctx(data, program, today, weight, fat, weight_date, fat_date, goals):
    w_avg_series = data.get('weightMovingAvg7') or []
    f_avg_series = data.get('fatMovingAvg7') or []
    w7 = _last_avg(w_avg_series)
    f7 = _last_avg(f_avg_series)
    if weight is None:
        weight = _last_val(data.get('weightHistory'))
    if fat is None:
        fat = _last_val(data.get('fatHistory'))
    w7_prev = _avg_at(w_avg_series, 28)
    f7_prev = _avg_at(f_avg_series, 28)
    wp = (program or {}).get('weightPlan') or {}
    cut = cut_status(wp, today, w7)
    # Blok 6: data.body (modules/body.py) bærer glidepath-status, korridor,
    # fedtfri masse og cut-tjek. Lægges på cut når det findes, så coachen
    # kan sige "foran/bagud" med samme tal som Krop-fanen.
    b = data.get('body') if isinstance(data.get('body'), dict) else None
    if b:
        g = b.get('glidepath') or {}
        m = b.get('ffm') or {}
        c = b.get('cutCheck') or {}
        cut = dict(cut)
        cut.update(_compact({
            'phase': g.get('phase'), 'status': g.get('status'),
            'expectedKg': _num(g.get('expectedKg')) if g.get('expectedKg') is not None else cut.get('expectedKg'),
            'corridorKg': _num(g.get('corridorKg')), 'actualRatePerWeek4w': _num(g.get('actualRate4w'), 2),
            'ffmKg': _num(m.get('now')), 'ffmChange28d': _num(m.get('change28d')), 'ffmTargetKg': _num(m.get('target')),
            'fatAvg14': _num((b.get('fat') or {}).get('avg14')), 'fatExpected': _num((b.get('fat') or {}).get('expected')),
            'checkLevel': c.get('level') if c.get('active') else None,
            'checkText': c.get('text') if c.get('active') else None,
            'alcohol7d': ((c.get('signals') or {}).get('alcohol') or {}).get('value') if c.get('active') else None,
        }))
    return {
        'weight': _num(weight), 'weightDate': weight_date, 'weightAvg7': _num(w7),
        'weightAvg7Change28d': _num(w7 - w7_prev) if (w7 is not None and w7_prev is not None) else None,
        'fat': _num(fat), 'fatDate': fat_date, 'fatAvg7': _num(f7),
        'fatAvg7Change28d': _num(f7 - f7_prev) if (f7 is not None and f7_prev is not None) else None,
        'weightGoal': _num(goals.get('weightKg')), 'fatGoal': _num(goals.get('bodyFatPct')),
        'weightToGoal': _num(w7 - float(goals['weightKg'])) if (w7 is not None and goals.get('weightKg') is not None) else None,
        'cut': cut,
    }


def _habits_ctx(data, af_streak, goals):
    af = data.get('af') or {}
    hist = [w for w in (data.get('af_history') or []) if isinstance(w, dict) and w.get('total')]
    full = [w for w in hist if w.get('total') == 7] or hist
    last4 = full[-4:]
    af_avg4 = round(sum(w['done'] for w in last4) / len(last4), 1) if last4 else None
    log = data.get('checkinLog') or []
    last7 = log[-7:]
    kinds = {'faa': 0, 'mange': 0, 'drak': 0}
    for e in last7:
        a = e.get('alkohol')
        if a == 1:
            kinds['faa'] += 1
        elif a == 2:
            kinds['mange'] += 1
    protein_days = sum(1 for e in last7 if e.get('protein') == 2)
    protein_reg = sum(1 for e in last7 if e.get('protein') is not None)
    energies = [e['energi'] for e in last7 if e.get('energi') is not None]
    hunger = sum(1 for e in last7 if e.get('sult') == 2)
    return {
        'afWeek': _int(af.get('weekDone')), 'afTarget': _int(goals.get('afDaysPerWeek', af.get('target'))),
        'afStreak': _int(af_streak if af_streak is not None else af.get('streak')),
        'afAvg4': af_avg4,
        'afKinds7': {'faa': kinds['faa'], 'mange': kinds['mange']},
        'proteinDays7': protein_days, 'proteinRegistered7': protein_reg,
        'energyAvg7': _avg(energies), 'hungerDays7': hunger,
    }


def _next_race_ctx(plan, athlete, today):
    up = _programs.upcoming_races(plan, athlete, today)
    if not up:
        return None
    r = up[0]
    return {'name': r.get('name'), 'date': r.get('date'), 'daysTo': _int(r.get('daysTo')),
            'priority': r.get('priority') or None, 'distance': r.get('distance')}


def _flags_ctx(plan_tab, program):
    out = []
    for w in ((plan_tab or {}).get('weeks') or []):
        if w.get('isCurrent') and (not program or w.get('programId') == program.get('id')):
            for f in w.get('flags', []):
                out.append({'level': f.get('level'), 'rule': f.get('rule'), 'text': f.get('text')})
    return out


def _rules_ctx(lib, program, goals):
    try:
        r = _bike.meta(lib).get('rules', {})
    except Exception:
        r = {}
    wp = (program or {}).get('weightPlan') or {}
    return _compact({
        'maxHaard': _int(r.get('maxHaardPerWeek')), 'maxModerat': _int(r.get('maxModeratPerWeek')),
        'minHoursBetweenHaard': _int(r.get('minHoursBetweenHaard', _plan_tab.MIN_HOURS_HARD)),
        'tsbFloor': _friel.TSB_FLOOR, 'rampSoft': _friel.RAMP_SOFT, 'rampHard': _friel.RAMP_HARD,
        'maxRunsPerWeek': _friel.MAX_RUNS_PER_WEEK,
        'cutRateKgPerWeek': _num(wp.get('maxLossPerWeekKg'), 2),
        'proteinG': _int(goals.get('proteinGPerDay')) if goals.get('proteinGPerDay') else None,
        'afTarget': _int(goals.get('afDaysPerWeek')),
        'sleepH': _num(goals.get('sleepHours')), 'sleepHMax': SLEEP_H_MAX,
        'strengthPerWeek': _int(goals.get('strengthPerWeek')),
    })


def _next_week_ctx(plan_tab, program):
    """Næste kalenderuge fra planTab (til søndagens gennemgang)."""
    if not plan_tab:
        return None
    weeks = plan_tab.get('weeks') or []
    sess = plan_tab.get('sessions') or []
    idx = next((i for i, w in enumerate(weeks) if w.get('isCurrent')), None)
    if idx is None or idx + 1 >= len(weeks):
        return None
    w = weeks[idx + 1]
    days = []
    if idx + 1 < len(sess):
        for d in sess[idx + 1].get('days', []):
            days.append({'date': d.get('date'), 'weekday': d.get('weekday'),
                         'entries': [_entry_from_plan_tab(e) for e in d.get('entries', []) if not e.get('extra')]})
    return {
        'week': w.get('week'), 'programId': w.get('programId'), 'start': w.get('start'),
        'phase': w.get('phase'), 'blockType': w.get('blockType'), 'mesoWeek': w.get('mesoWeek'),
        'purpose': w.get('purpose'), 'note': w.get('note'),
        'ctlTarget': _num(w.get('ctlTarget')), 'tssTarget': _num(w.get('tssTarget'), 0),
        'quota': w.get('quota'), 'quotaUsed': w.get('quotaUsed'),
        'keySessions': w.get('keySessions'), 'races': w.get('races'), 'travel': w.get('travel'),
        'days': days,
    }


def catalog(lib=None):
    """Kælderkataloget som data — id, navn, minutter, belastning, kategori."""
    lib = lib or _bike.load()
    cats = _bike.meta(lib).get('categories', {})
    return [{'id': w['id'], 'name': w.get('name'), 'category': cats.get(w.get('category'), w.get('category')),
             'min': _int(w.get('est_min')), 'load': w.get('load'), 'erg': bool(w.get('erg', True))}
            for w in _bike.all_workouts(lib)]


# ── Hovedfunktion ───────────────────────────────────────────────────────────

def build_context(plan, data, today=None, *, athlete='kennet', lib=None,
                  ctl=None, atl=None, tsb=None, wellness=None,
                  weight=None, fat=None, weight_date=None, fat_date=None,
                  planned_tss=None, tss_actual=None, af_streak=None,
                  include_next_week=None, include_catalog=None, travel_label=None):
    """Byg coach-konteksten. Kan køres offline mod plan.json + data.json.

    plan        data/plan.json (dict)
    data        data-dict'et fra update_kpi (data.json + dagens felter: week_sessions,
                planTab, warnings, *History, *MovingAvg7, af, af_history, checkinLog,
                efTrend, aerobicFlag, ctlCurve, tsb)
    today       date/ISO (default: i dag)
    ctl/atl/tsb friske tal fra Intervals (fallback: data.ctlCurve / data.tsb)
    wellness    fitness.get_wellness_7d()-dict (fallback: historik i data)
    weight/fat  værdien coachen skal se (dagens eller seneste inden for 7 dage) +
                *_date når målingen ikke er fra i dag
    planned_tss / tss_actual  ugens planlagte og faktiske TSS
    include_next_week / include_catalog  default: søndag
    """
    today = _to_date(today) if today else date.today()
    lib = lib or _bike.load()
    program = _programs.active_program(plan, athlete, today)
    goals = dict((program or {}).get('goals') or {})
    plan_tab = data.get('planTab') if isinstance(data.get('planTab'), dict) else None
    if plan_tab and program and plan_tab.get('programId') != program.get('id'):
        plan_tab = None  # gammel planTab fra et andet program — brug ikke dens id'er
    week_sessions = data.get('week_sessions') or []
    wk = _programs.week_no(program, today) if program else None
    meta = _programs.week_meta(program, wk) if program else {}

    sunday = today.weekday() == 6
    if include_next_week is None:
        include_next_week = sunday
    if include_catalog is None:
        include_catalog = sunday

    if planned_tss is None:
        planned_tss = meta.get('tssTarget')

    ctx = {
        'program': _program_ctx(plan, program, today, athlete, lib),
        'today': _today_ctx(today, week_sessions, plan_tab),
        'week': _week_ctx(today, week_sessions, plan_tab, planned_tss, tss_actual),
        'fitness': _fitness_ctx(data, ctl, atl, tsb, meta.get('ctlTarget'), plan_tab),
        'readiness': _readiness_ctx(data, wellness),
        'body': _body_ctx(data, program, today, weight, fat, weight_date, fat_date, goals),
        'habits': _habits_ctx(data, af_streak, goals),
        'nextRace': _next_race_ctx(plan, athlete, today),
        'flags': _flags_ctx(plan_tab, program),
        'warnings': [{'type': w.get('type'), 'level': w.get('level'), 'message': w.get('message')}
                     for w in (data.get('warnings') or []) if isinstance(w, dict)],
        'travel': travel_label,
        'rules': _rules_ctx(lib, program, goals),
    }
    if include_next_week:
        ctx['nextWeek'] = _next_week_ctx(plan_tab, program)
    if include_catalog:
        ctx['catalog'] = catalog(lib)
    return ctx


def entry_ids(ctx):
    """Alle entry-id'er der findes i konteksten (dagens pas, ugens rest, kommende 14 dage)."""
    ids = set()
    for e in (ctx.get('today') or {}).get('sessions', []):
        if e.get('id'):
            ids.add(e['id'])
    wk = ctx.get('week') or {}
    for e in wk.get('remaining', []) + wk.get('upcoming', []):
        if e.get('id'):
            ids.add(e['id'])
    for d in ((ctx.get('nextWeek') or {}).get('days') or []):
        for e in d.get('entries', []):
            if e.get('id'):
                ids.add(e['id'])
    return ids


def inputs_hash(ctx):
    """sha1 af konteksten (den indeholder ingen tidsstempler — kun dagens dato)."""
    raw = json.dumps(ctx, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()
