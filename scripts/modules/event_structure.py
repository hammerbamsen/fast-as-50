# -*- coding: utf-8 -*-
"""Struktur-validering af Intervals-events (gelænder, 2026-07-22).

Baggrund: 22/7 stod et 16 km løb uden trin på uret kl. 06.35. Årsagen var at
Intervals bygger træningen ud fra `description` — IKKE fra `workout_doc`.
Eventet havde ren prosa i description, så der var intet at parse, og både
app og Garmin viste en tom træning. `workout_doc` var skrevet manuelt via API
og blev ignoreret.

Fejlen kan ikke fanges af plan_coherence, som læser plan.json. Events bygget
i hånden mod Intervals-API'et findes ikke i plan.json. Derfor validerer dette
modul de faktiske events fra Intervals.

Rene funktioner uden netværk — kaldes med allerede hentede events.
"""
import re

# Sportsgrene hvor et effekt-mål (power) er meningsløst og indikerer at
# Intervals har fejltolket et zone-navn i step-teksten. "Z1-Z2" i et
# step-navn bliver læst som power_zone 1-2.
_NO_POWER_TYPES = {'Run', 'VirtualRun', 'TrailRun', 'Swim', 'OpenWaterSwim'}

# En struktureret description har mindst én linje der starter med "- ".
# Gentagelsesblokke skrives som "5x" på egen linje.
_STEP_LINE = re.compile(r'^\s*-\s+\S', re.MULTILINE)
_REPEAT_LINE = re.compile(r'^\s*\d+\s*x\s*$', re.MULTILINE)


def _has_structured_description(desc):
    """True hvis description indeholder Intervals' workout-syntaks."""
    if not desc or not desc.strip():
        return False
    return bool(_STEP_LINE.search(desc) or _REPEAT_LINE.search(desc))


def _iter_steps(steps):
    """Fladgør trin inkl. gentagelsesblokke."""
    for s in steps or []:
        if isinstance(s, dict) and s.get('steps'):
            for inner in _iter_steps(s['steps']):
                yield inner
        elif isinstance(s, dict):
            yield s


def check_event(ev):
    """Returnér liste af problemer for ét event. Tom liste = OK."""
    problems = []

    if ev.get('category') != 'WORKOUT':
        return problems
    if ev.get('show_as_note'):
        return problems

    ev_type = ev.get('type') or ''
    desc = ev.get('description') or ''
    doc = ev.get('workout_doc') or {}
    steps = list(_iter_steps(doc.get('steps')))

    # Regel 1 — den fejl der ramte 22/7: prosa i stedet for syntaks.
    if not _has_structured_description(desc):
        problems.append({
            'level': 'error',
            'code': 'PROSA_BESKRIVELSE',
            'text': 'Beskrivelsen har ingen workout-syntaks (linjer med "- "). '
                    'Intervals kan ikke bygge trin — uret får en tom traening.',
        })

    # Regel 2 — uanset årsag: ingen trin at sende til uret.
    if not steps:
        problems.append({
            'level': 'error',
            'code': 'INGEN_TRIN',
            'text': 'workout_doc har ingen trin.',
        })

    # Regel 3 — spøgelses-effektzoner fra zone-navne i step-tekst.
    if ev_type in _NO_POWER_TYPES:
        ghost = sum(1 for s in steps if 'power' in s)
        if ghost:
            problems.append({
                'level': 'warn',
                'code': 'SPOEGELSES_POWER',
                'text': f'{ghost} trin har effekt-maal paa {ev_type}. '
                        'Skyldes typisk "Z1-Z2" i et step-navn — omdoeb trinnet.',
            })

    # Regel 4 — dobbelt målsætning oveni en struktur.
    if steps:
        for felt in ('distance_target', 'time_target'):
            if ev.get(felt):
                problems.append({
                    'level': 'warn',
                    'code': 'DOBBELT_MAAL',
                    'text': f'{felt}={ev[felt]} er sat oveni en struktureret traening. '
                            'Ryd feltet ved at PUT\'e vaerdien 0 (null virker ikke).',
                })

    return problems


def check_events(events):
    """Validér en liste events. Returnér flad liste af advarsler til data.json."""
    out = []
    for ev in events or []:
        for p in check_event(ev):
            out.append({
                'date': (ev.get('start_date_local') or '')[:10],
                'name': ev.get('name') or '?',
                'type': ev.get('type') or '?',
                'event_id': ev.get('id'),
                'level': p['level'],
                'code': p['code'],
                'text': p['text'],
            })
    out.sort(key=lambda w: (w['date'], w['level'] != 'error'))
    return out
