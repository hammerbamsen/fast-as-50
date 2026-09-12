"""Check-in-historik (alkohol/protein/energi/aftensult) fra Intervals wellness.

Kilde er de samme wellness-rækker som AF-loggen (af.py). Feltnavne i Intervals:
  Alkohol    (custom)  0 = AF-dag, 1 = drak (bevidst valgt), 2 = drak (bare skete)
  protein    (custom)  2 = protein i 3 af 3 hovedmåltider, 1 = 2 af 3, 0 = ≤1
  motivation (Intervals-skala 1-4; 5 afvises med 422) — bruges som energi: 1 lav, 3 ok, 4 høj
  Aftensult  (custom)  0 = nej, 1 = lidt, 2 = ja

Alt her er rene funktioner over en liste af wellness-rækker, så det kan testes
uden netværk. Kun get_checkin_log() henter.
"""
from datetime import date, timedelta

from .config import BASE, AUTH, api_get

LOG_DAYS = 28
FIELD_ALKOHOL = 'Alkohol'
FIELD_PROTEIN = 'protein'
FIELD_ENERGI  = 'motivation'
FIELD_SULT    = 'Aftensult'

# Alkohol-værdi 1/2 -> hvordan drikkedagen blev registreret (0 = AF-dag).
ALKOHOL_KIND = {1: 'valgt', 2: 'autopilot'}


def _int_or_none(v):
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def build_checkin_log(rows, today=None, days=LOG_DAYS):
    """Liste af de sidste `days` dage (ældst først), én dict pr. dag:
    {date, alkohol, protein, energi, sult} — None hvor intet er registreret.
    Dage uden wellness-række er med (alle felter None), så frontend altid
    kan tegne 7 prikker uden at gætte datoer.
    """
    if today is None:
        today = date.today()
    by_date = {}
    for r in rows or []:
        k = (r.get('id') or r.get('date') or '')[:10]
        if k:
            by_date[k] = r
    out = []
    for offset in range(days - 1, -1, -1):
        d = today - timedelta(days=offset)
        r = by_date.get(str(d), {})
        out.append({
            'date':    str(d),
            'alkohol': _int_or_none(r.get(FIELD_ALKOHOL)),
            'protein': _int_or_none(r.get(FIELD_PROTEIN)),
            'energi':  _int_or_none(r.get(FIELD_ENERGI)),
            'sult':    _int_or_none(r.get(FIELD_SULT)),
        })
    return out


def _last(log, n):
    return (log or [])[-n:] if n else []


def protein_days(log, n=7):
    """Antal dage i de sidste n med protein == 2 (3 af 3 måltider)."""
    return sum(1 for e in _last(log, n) if e.get('protein') == 2)


def protein_weekly_avg(log, weeks=4):
    """Snit af 3/3-dage pr. uge over de sidste `weeks` uger (kun hele uger
    der findes i loggen). None hvis under 7 dage."""
    log = log or []
    if len(log) < 7:
        return None
    n_weeks = min(weeks, len(log) // 7)
    total = protein_days(log, n_weeks * 7)
    return round(total / n_weeks, 1)


def protein_kpi(log):
    """KPI-dict til data.kpis.protein: 3/3-dage sidste 7 af 7."""
    n = protein_days(log, 7)
    registered = sum(1 for e in _last(log, 7) if e.get('protein') is not None)
    avg = protein_weekly_avg(log)
    sub = '3/3-dage'
    if avg is not None:
        sub += f" · 4 uger {str(avg).replace('.', ',')}"
    if registered == 0:
        color = '#7A6A58'
    elif n >= 5:
        color = '#27AE60'
    elif n >= 3:
        color = '#E67E22'
    else:
        color = '#C0392B'
    return {'value': str(n), 'unit': '/7', 'sub': sub, 'color': color}


def energy_avg(log, n=7):
    """Snit af energi (1-4) over de sidste n dage med registrering, 1 decimal."""
    vals = [e['energi'] for e in _last(log, n) if e.get('energi') is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def hunger_days(log, n=7):
    """Dage i de sidste n med aftensult == 2 (ja)."""
    return sum(1 for e in _last(log, n) if e.get('sult') == 2)


# Før 4/9-2026 betød Alkohol=1 blot "drak" (den gamle af.html, slettet blok 9). Valgt/autopilot-skelnen
# findes først fra log-arket i v2.0 — ældre 1'ere må ikke vises som "valgt".
KIND_CUTOVER = '2026-09-04'


def af_kinds(log):
    """{dato: 'valgt'|'autopilot'|'drak'} for drikkedage (1/2). Før KIND_CUTOVER: 'drak'."""
    out = {}
    for e in (log or []):
        a = e.get('alkohol')
        if a in ALKOHOL_KIND:
            out[e['date']] = ALKOHOL_KIND[a] if e['date'] >= KIND_CUTOVER else 'drak'
    return out


def coach_line(log):
    """Én linje til coach-prompten — None hvis intet er registreret sidste 7 dage."""
    last7 = _last(log, 7)
    if not any(e.get('protein') is not None or e.get('sult') is not None
               or e.get('energi') is not None for e in last7):
        return None
    parts = [f"Protein 3/3-dage sidste 7: {protein_days(log, 7)}",
             f"aftensult-dage: {hunger_days(log, 7)}"]
    e = energy_avg(log, 7)
    parts.append(f"energi-snit: {str(e).replace('.', ',')}" if e is not None else "energi-snit: —")
    return ' · '.join(parts)


def get_checkin_log(days=LOG_DAYS, today=None):
    """Henter wellness for de sidste `days` dage og bygger loggen. [] ved fejl."""
    if today is None:
        today = date.today()
    oldest = today - timedelta(days=days - 1)
    r = api_get(f'{BASE}/wellness', auth=AUTH,
                params={'oldest': str(oldest), 'newest': str(today)})
    if not r or r.status_code != 200:
        return []
    log = build_checkin_log(r.json(), today=today, days=days)
    print(f"  Check-in log: {sum(1 for e in log if e['protein'] is not None)} dage med protein, "
          f"{sum(1 for e in log if e['sult'] is not None)} med aftensult")
    return log
