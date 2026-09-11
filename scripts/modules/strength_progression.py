"""Styrke-progression styret af et check-in hver 4. uge (blok 10, 9/9-2026; 14 → 28 dage 11/9-2026).

Erstatter RPE-loggen pr. pas. Hver anden søndag (fra CHECKIN_START) svarer
Kennet på to ja/nej i I dag:
  ben:      "Alle runder × reps med RPE ≤ 7 på de sidste 2 pas?"
  overkrop: samme (core tæller som overkrop)
Svaret gemmes af plan-edit (action strength_checkin) i
plan.athletes.kennet.strengthCheckin[søndag] = {legs, upper, at}, og
progressionen i plan.athletes.kennet.strengthProgression:

  {"current":  {"ben": {"step": n}, "overkrop": {"step": n, "extraReps": r}},
   "previous": {...},            # tilstanden før seneste check-in
   "effectiveFrom": "YYYY-MM-DD", # current gælder for pas fra denne dato
   "updatedAt": ISO, "lastCheckin": "YYYY-MM-DD"}

Regler (workout_library progression, omskrevet til check-in):
  ben ja      -> step + 1 (næste trin på øvelsens stige: KB 12,5→16→20,
                 DB 5→7→10→12,5→15). Loftet er hjemme-gymmets største vægt.
  overkrop ja -> extraReps + 2 op til +4; ved +4 -> step + 1 og extraReps 0.
  nej         -> uændret.
  recovery    -> hvis ugen efter check-in'et er en recovery-uge (styrke-entry
                 med "recovery" i note), gælder den nye tilstand først fra
                 mandagen efter recovery-ugen. Recovery-ugen kører previous.

Alt er rene funktioner uden I/O. Loads i templates er tekst ("2×5 kg DB",
"12,5 kg KB goblet") og parses/formatteres her; ukendt format = uændret.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

CHECKIN_START = date(2026, 10, 4)      # første søndag; 14 dage efter cut-start 21/9
CHECKIN_INTERVAL_DAYS = 28   # 11/9-2026: månedligt — 14 dage var for tæt
DB_LADDER = [5.0, 7.0, 10.0, 12.5, 15.0]
KB_LADDER = [12.5, 16.0, 20.0]
MAX_EXTRA_REPS = 4
GROUP_OF = {'ben': 'ben', 'overkrop': 'overkrop', 'core': 'overkrop'}

_LOAD_RE = re.compile(r'^\s*(?:(\d+)\s*[×x]\s*)?(\d+(?:[.,]\d+)?)\s*kg\b\s*(KB|DB)?(.*)$', re.I)


def _to_date(d):
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d)[:10])


def _fmt_kg(v):
    s = f"{v:.1f}".rstrip('0').rstrip('.')
    return s.replace('.', ',')


def empty_state():
    return {'ben': {'step': 0}, 'overkrop': {'step': 0, 'extraReps': 0}}


def _norm_group_state(st):
    st = dict(st or {})
    out = {'ben': {'step': int((st.get('ben') or {}).get('step') or 0)},
           'overkrop': {'step': int((st.get('overkrop') or {}).get('step') or 0),
                        'extraReps': int((st.get('overkrop') or {}).get('extraReps') or 0)}}
    return out


def parse_load(load):
    """'2×5 kg DB' -> {count 2, kg 5.0, equip 'DB', tail ''}; None hvis ukendt."""
    if load is None:
        return None
    if isinstance(load, (int, float)):
        return {'count': None, 'kg': float(load), 'equip': None, 'tail': ''}
    m = _LOAD_RE.match(str(load))
    if not m:
        return None
    cnt, kg, equip, tail = m.groups()
    kg = float(kg.replace(',', '.'))
    equip = (equip or '').upper() or None
    if equip is None:
        equip = 'KB' if re.search(r'\bkb\b|kettlebell|goblet', str(load), re.I) else 'DB'
    return {'count': int(cnt) if cnt else None, 'kg': kg, 'equip': equip, 'tail': (tail or '').strip()}


def format_load(p):
    s = f"{p['count']}×" if p.get('count') else ''
    s += f"{_fmt_kg(p['kg'])} kg"
    if p.get('equip'):
        s += f" {p['equip']}"
    if p.get('tail'):
        s += f" {p['tail']}"
    return s


def step_load(load, step):
    """Løft `load` `step` trin op ad stigen. Returnerer (ny_load_tekst, capped)."""
    p = parse_load(load)
    if p is None or step <= 0:
        return load, False
    ladder = KB_LADDER if p['equip'] == 'KB' else DB_LADDER
    try:
        i = ladder.index(p['kg'])
    except ValueError:
        # Basisvægt ikke på stigen: nærmeste trin over.
        above = [v for v in ladder if v > p['kg']]
        if not above:
            return load, True
        i = ladder.index(above[0]) - 1
    j = min(i + step, len(ladder) - 1)
    capped = (i + step) > (len(ladder) - 1)
    q = dict(p, kg=ladder[j])
    return format_load(q), capped


def apply_state(exercises, state):
    """Template-øvelser + tilstand -> ny øvelsesliste med progression lagt på.
    Hver øvelse får `baseLoad`/`baseReps` og evt. `capped` (max vægt hjemme)."""
    st = _norm_group_state(state)
    out = []
    for e in (exercises or []):
        e2 = dict(e)
        e2['baseLoad'] = e.get('load')
        e2['baseReps'] = e.get('reps')
        g = GROUP_OF.get(str(e.get('group') or '').lower())
        if g == 'ben':
            e2['load'], e2['capped'] = step_load(e.get('load'), st['ben']['step'])
        elif g == 'overkrop':
            e2['load'], e2['capped'] = step_load(e.get('load'), st['overkrop']['step'])
            unit = str(e.get('unit') or '')
            if isinstance(e.get('reps'), int) and unit.lower().startswith('reps'):
                e2['reps'] = e['reps'] + st['overkrop']['extraReps']
        out.append(e2)
    return out


def advance(state, legs_yes, upper_yes):
    """Ren progression af tilstanden ud fra to ja/nej."""
    st = _norm_group_state(state)
    if legs_yes:
        st['ben']['step'] += 1
    if upper_yes:
        if st['overkrop']['extraReps'] < MAX_EXTRA_REPS:
            st['overkrop']['extraReps'] = min(MAX_EXTRA_REPS, st['overkrop']['extraReps'] + 2)
        else:
            st['overkrop']['step'] += 1
            st['overkrop']['extraReps'] = 0
    return st


def week_of(d):
    d = _to_date(d)
    mon = d - timedelta(days=d.weekday())
    return mon, mon + timedelta(days=6)


def is_recovery_week(days, mon):
    """True hvis et styrkepas i ugen fra `mon` har 'recovery' i note/name."""
    mon = _to_date(mon)
    sun = mon + timedelta(days=6)
    for d in (days or []):
        ds = str(d.get('date') or '')[:10]
        if not ds or ds < mon.isoformat() or ds > sun.isoformat():
            continue
        for e in d.get('entries') or []:
            wo = e.get('workout') or {}
            if wo.get('type') not in ('WeightTraining', 'Workout', 'Strength'):
                continue
            txt = f"{e.get('note') or ''} {wo.get('name') or ''} {wo.get('description') or ''}".lower()
            if 'recovery' in txt:
                return True
    return False


def apply_checkin(progression, checkin_date, legs_yes, upper_yes, days, now=None):
    """Ny strengthProgression-blok efter et check-in på `checkin_date`
    (søndag). `days` = plan.athletes.kennet.days til recovery-opslag."""
    checkin_date = _to_date(checkin_date)
    now = now or datetime.now(timezone.utc)
    prog = progression if isinstance(progression, dict) else {}
    cur = _norm_group_state(prog.get('current') or empty_state())
    nxt = advance(cur, legs_yes, upper_yes)
    next_mon = checkin_date + timedelta(days=1)
    next_mon -= timedelta(days=next_mon.weekday())
    eff = next_mon
    if is_recovery_week(days, next_mon):
        eff = next_mon + timedelta(days=7)
    return {'current': nxt, 'previous': cur, 'effectiveFrom': eff.isoformat(),
            'updatedAt': now.replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
            'lastCheckin': checkin_date.isoformat()}


def state_for_date(progression, d):
    """Tilstanden der gælder for et pas på dato d (current fra effectiveFrom, ellers previous)."""
    prog = progression if isinstance(progression, dict) else {}
    if not prog.get('current'):
        return empty_state()
    eff = prog.get('effectiveFrom')
    if eff and _to_date(d) < _to_date(eff):
        return _norm_group_state(prog.get('previous') or empty_state())
    return _norm_group_state(prog['current'])


def state_summary(state):
    st = _norm_group_state(state)
    parts = []
    parts.append(f"Ben trin {st['ben']['step']}" if st['ben']['step'] else 'Ben grundvægt')
    o = st['overkrop']
    base = f"Overkrop trin {o['step']}" if o['step'] else 'Overkrop grundvægt'
    parts.append(base + (f" +{o['extraReps']} reps" if o['extraReps'] else ''))
    return ' · '.join(parts)


def due_dates(today, start=CHECKIN_START, interval=CHECKIN_INTERVAL_DAYS):
    """Alle check-in-søndage til og med i dag (ældst -> nyest)."""
    today = _to_date(today)
    out, d = [], start
    while d <= today:
        out.append(d)
        d += timedelta(days=interval)
    return out


def build_checkin(checkins, progression, today, days=None):
    """data['strengthCheckin'] = {due, date, question, next, last, state,
    stateSummary, recoveryNext}. `due` er True når seneste check-in-søndag
    ≤ i dag ikke er besvaret. Kortet i I dag viser sig når due er True."""
    today = _to_date(today)
    cis = checkins if isinstance(checkins, dict) else {}
    dues = due_dates(today)
    latest = dues[-1] if dues else None
    answered = latest is not None and latest.isoformat() in cis
    nxt = (latest + timedelta(days=CHECKIN_INTERVAL_DAYS)) if latest else CHECKIN_START
    last_key = max(cis.keys()) if cis else None
    last = None
    if last_key:
        rec = cis.get(last_key) or {}
        last = {'date': last_key, 'legs': rec.get('legs'), 'upper': rec.get('upper'), 'at': rec.get('at')}
    cur = state_for_date(progression, today)
    next_mon = (latest + timedelta(days=1)) if latest else None
    rec_next = bool(next_mon and is_recovery_week(days, next_mon))
    return {'due': bool(latest and not answered),
            'date': latest.isoformat() if latest else None,
            'next': nxt.isoformat(),
            'question': 'Alle runder × reps med RPE ≤ 7 på de sidste 2 pas?',
            'recoveryNext': rec_next,
            'last': last,
            'state': cur,
            'stateSummary': state_summary(cur),
            'effectiveFrom': (progression or {}).get('effectiveFrom') if isinstance(progression, dict) else None}
