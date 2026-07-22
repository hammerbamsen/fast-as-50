# -*- coding: utf-8 -*-
"""Tests for event_structure.py — gelænder mod trinløse Intervals-events."""
from . import event_structure as es

# Det faktiske event fra 22/7 der fejlede: prosa-beskrivelse, håndskrevet
# workout_doc som Intervals ignorerede, plus distance_target sat.
BROKEN_22_7 = {
    'id': 123721447,
    'category': 'WORKOUT',
    'type': 'Run',
    'name': 'Løb 16 km Z1–Z2 til fyret',
    'start_date_local': '2026-07-22T00:00:00',
    'description': 'Roligt aerobt til fyret. Hold Z1–Z2, beskyt lilletåen.',
    'distance_target': 16000.0,
    'workout_doc': {'steps': [
        {'duration': 600, 'pace': {'start': 65, 'end': 78, 'units': '%pace'}},
    ]},
}

# Et event der virker: syntaks i description.
GOOD_RUN = {
    'id': 1,
    'category': 'WORKOUT',
    'type': 'Run',
    'name': 'Løb VO2 5×3 min Z4',
    'start_date_local': '2026-07-14T00:00:00',
    'description': ('- Varm-op 15m >5:35/km Pace\n\n5x\n'
                    '- Interval 3m 4:13-4:25/km Pace\n'
                    '- Pause 2m >5:35/km Pace\n\n'
                    '- Cool-down 10m >5:35/km Pace'),
    'workout_doc': {'steps': [
        {'duration': 900, 'pace': {'value': 335, 'units': 'secs/km'}},
        {'reps': 5, 'steps': [
            {'duration': 180, 'pace': {'start': 253, 'end': 265, 'units': 'secs/km'}},
            {'duration': 120, 'pace': {'value': 335, 'units': 'secs/km'}},
        ]},
        {'duration': 600, 'pace': {'value': 335, 'units': 'secs/km'}},
    ]},
}


def test_prosa_beskrivelse_fanges():
    """Kernefejlen 22/7: prosa i stedet for workout-syntaks."""
    koder = [p['code'] for p in es.check_event(BROKEN_22_7)]
    assert 'PROSA_BESKRIVELSE' in koder
    assert 'DOBBELT_MAAL' in koder


def test_godt_loeb_giver_ingen_problemer():
    assert es.check_event(GOOD_RUN) == []


def test_gentagelsesblok_taelles_som_trin():
    """5x-blokken må ikke få modulet til at tro der er få/ingen trin."""
    flad = list(es._iter_steps(GOOD_RUN['workout_doc']['steps']))
    assert len(flad) == 4


def test_ingen_trin_fanges():
    ev = dict(GOOD_RUN, workout_doc={'steps': []}, id=2)
    assert 'INGEN_TRIN' in [p['code'] for p in es.check_event(ev)]


def test_spoegelses_power_paa_loeb():
    ev = dict(GOOD_RUN, id=3, workout_doc={'steps': [
        {'duration': 600, 'pace': {'value': 335, 'units': 'secs/km'},
         'power': {'start': 1, 'end': 2, 'units': 'power_zone'}},
    ]})
    assert 'SPOEGELSES_POWER' in [p['code'] for p in es.check_event(ev)]


def test_power_paa_cykel_er_lovligt():
    ev = {'id': 4, 'category': 'WORKOUT', 'type': 'Ride', 'name': 'Cykel Z2',
          'start_date_local': '2026-08-01T00:00:00',
          'description': '- Z2 60m 56-76% FTP',
          'workout_doc': {'steps': [
              {'duration': 3600, 'power': {'start': 56, 'end': 76, 'units': '%ftp'}}]}}
    assert es.check_event(ev) == []


def test_race_og_noter_springes_over():
    assert es.check_event({'category': 'RACE_A', 'description': 'Médoc'}) == []
    assert es.check_event({'category': 'WORKOUT', 'show_as_note': True,
                           'description': 'Husk startnummer'}) == []


def test_check_events_sorterer_fejl_foerst():
    ud = es.check_events([GOOD_RUN, BROKEN_22_7])
    assert ud[0]['date'] == '2026-07-22'
    assert ud[0]['level'] == 'error'
    assert all(w['event_id'] == 123721447 for w in ud)
