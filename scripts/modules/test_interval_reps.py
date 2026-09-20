# -*- coding: utf-8 -*-
"""Tests for rep-for-rep-analyse af intervalpas.

Baggrund: sessionsgennemsnittet kan ikke vurdere et intervalpas. På 4×5 min med
15 min opvarmning, 9 min pauser og 10 min cool-down er 30% tid-i-zone det
matematiske maksimum. Dagens VO2-pas (6/8-26) scorede 110,9% i Intervals'
compliance — men 2 af 4 reps blev løbet i Z5, ikke Z4.

fixtures_vo2_run.json er den rigtige payload fra /activity/i172960909/intervals.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from modules import sessions as _sessions_mod
from modules.sessions import (get_interval_reps, summarize_reps, count_planned_reps,
                              bike_zone_watts, planned_target_from_event,
                              _half_drift, _pace_str)

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures_vo2_run.json')

# Disse tests (inkl. den rigtige VO2-fixture fra 6/8-26) er skrevet mod
# løbetærsklen som den var dengang: 264 sek/km (4:24/km). thresholdSec
# ændrer sig i produktion (fx efter en tempo-/FTP-test), og hele pointen
# med sessions.py er at zonerne ALTID følger plan.json live. Så pin
# tærsklen/zonetabellen her i testene -- ellers brækker CI hver gang
# thresholdSec opdateres i produktion, uden at koden faktisk fejler.
_FIXED_THRESHOLD_SEC = 264
_FIXED_RUN_ZONES = {
    'Z1': (339, 99999),
    'Z2': (300, 338),
    'Z3': (270, 299),
    'Z4': (257, 269),
    'Z5': (236, 256),
    'Z6': (0, 235),
}


@pytest.fixture(autouse=True)
def _pinned_run_threshold(monkeypatch):
    plan = _sessions_mod._PLAN or {}
    zones = dict(((plan.get('athletes', {}) or {}).get('kennet', {}) or {}).get('zones') or {})
    zones['thresholdSec'] = _FIXED_THRESHOLD_SEC
    monkeypatch.setattr(_sessions_mod, '_PLAN', {'athletes': {'kennet': {'zones': zones}}})
    monkeypatch.setattr(_sessions_mod, 'RUN_PACE_ZONES_SEC_PER_KM', _FIXED_RUN_ZONES)


def load_fixture():
    with open(FIXTURE, encoding='utf-8') as f:
        return json.load(f)


def mk(secs, pace_sec=None, watts=None, hr=150, start=0, end=0):
    """Byg et detekteret interval-stykke."""
    return {
        'moving_time': secs,
        'average_speed': (1000.0 / pace_sec) if pace_sec else None,
        'average_watts': watts,
        'average_heartrate': hr,
        'start_index': start,
        'end_index': end,
        'type': 'WORK',
        'label': None,
    }


# ── Rigtige data: dagens VO2-pas ─────────────────────────────────────────────

def test_fixture_giver_fire_reps():
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=load_fixture())
    assert len(reps) == 4


def test_fixture_reps_har_korrekt_varighed():
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=load_fixture())
    # Planlagt 5 min pr. rep -- alle skal lande på 299-300 sek
    assert all(299 <= r['secs'] <= 300 for r in reps)


def test_fixture_fanger_overpacing_paa_rep_1_og_3():
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=load_fixture())
    assert [r['flag'] for r in reps] == ['fast', 'ok', 'fast', 'ok']


def test_fixture_pace_er_vaegtet_over_de_merged_stykker():
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=load_fixture())
    # Rep 1 = 254s@4:13 + 46s@4:09 -> vægtet 4:13, ikke 4:11 (simpelt snit)
    assert 252 <= reps[0]['pace_sec'] <= 254


def test_fixture_pauser_og_opvarmning_taeller_ikke_med():
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=load_fixture())
    # 15 min opvarmning + 3×3 min pause + 10 min cool-down må aldrig blive reps
    assert sum(r['secs'] for r in reps) < 1300


def test_fixture_summary_naevner_overpacing_og_ikke_drop_off():
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=load_fixture())
    line = summarize_reps(reps, 'Z4', 'run', planned_reps=4)
    assert 'HÅRDERE end target' in line
    assert 'target 4:17–4:29/km' in line
    # Vekslende pace er overpacing, ikke udtrætning
    assert 'drop-off' not in line


# ── Syntetiske scenarier ─────────────────────────────────────────────────────

def test_perfekt_jaevn_udfoerelse():
    iv = [mk(300, 262), mk(180, 330), mk(300, 261), mk(180, 330), mk(300, 263)]
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=iv)
    assert len(reps) == 3
    assert all(r['flag'] == 'ok' for r in reps)
    assert 'jævnt udført' in summarize_reps(reps, 'Z4', 'run')


def test_drop_off_fanges():
    iv = [mk(300, 258), mk(180, 330), mk(300, 259), mk(180, 330),
          mk(300, 268), mk(180, 330), mk(300, 269)]
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=iv)
    line = summarize_reps(reps, 'Z4', 'run')
    assert 'drop-off' in line and 'sek/km' in line


def test_negative_split_fanges():
    iv = [mk(300, 269), mk(180, 330), mk(300, 268), mk(180, 330),
          mk(300, 259), mk(180, 330), mk(300, 258)]
    line = summarize_reps(get_interval_reps('x', 'Z4', 'run', streams={}, intervals=iv),
                          'Z4', 'run')
    assert 'negative split' in line


def test_for_langsomme_reps_flages():
    iv = [mk(300, 285), mk(180, 340), mk(300, 288)]
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=iv)
    assert [r['flag'] for r in reps] == ['slow', 'slow']
    assert 'nåede ikke op på target' in summarize_reps(reps, 'Z4', 'run')


def test_manglende_reps_paatales():
    iv = [mk(300, 262), mk(180, 330), mk(300, 261)]
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=iv)
    line = summarize_reps(reps, 'Z4', 'run', planned_reps=4)
    assert '4 reps var planlagt, 2 udført' in line


def test_pas_uden_rep_struktur_giver_tom_liste():
    # Jævnt Z2-løb: intet ligger hurtigere end Z4-tolerancen
    iv = [mk(2700, 320)]
    assert get_interval_reps('x', 'Z4', 'run', streams={}, intervals=iv) == []


def test_korte_stoej_stykker_ignoreres():
    iv = [mk(8, 240), mk(300, 262), mk(180, 330), mk(5, 230), mk(300, 263)]
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=iv)
    assert len(reps) == 2


def test_tom_input_crasher_ikke():
    assert get_interval_reps('x', 'Z4', 'run', streams={}, intervals=[]) == []
    assert get_interval_reps(None, 'Z4', 'run') == []
    assert get_interval_reps('x', 'Zx', 'run', streams={}, intervals=[mk(300, 260)]) == []
    assert get_interval_reps('x', 'Z4', 'swim', streams={}, intervals=[mk(300, 260)]) == []
    assert summarize_reps([], 'Z4', 'run') is None


def test_in_zone_pct_beregnes_fra_stream():
    # 100 samples: 60 i Z4 (260 sek/km), 40 hurtigere (240 sek/km)
    vel = [1000.0 / 260] * 60 + [1000.0 / 240] * 40
    iv = [mk(100, 252, start=0, end=99)]
    reps = get_interval_reps('x', 'Z4', 'run',
                             streams={'velocity_smooth': vel}, intervals=iv)
    assert reps[0]['in_zone_pct'] == 60.0


# ── Cykel ────────────────────────────────────────────────────────────────────

def test_bike_zone_watts_fra_ftp():
    assert bike_zone_watts('Z4') == (252, 293)


def test_bike_reps_paa_watt():
    iv = [mk(300, watts=270, hr=150), mk(240, watts=120, hr=120),
          mk(300, watts=310, hr=160)]
    reps = get_interval_reps('x', 'Z4', 'bike', streams={}, intervals=iv)
    assert len(reps) == 2
    assert [r['flag'] for r in reps] == ['ok', 'fast']
    assert 'target 252–293W' in summarize_reps(reps, 'Z4', 'bike')


# ── Hjælpefunktioner ─────────────────────────────────────────────────────────

def test_half_drift_ignorerer_vekslende_tempo():
    assert _half_drift([253, 260, 252, 259]) == -1


def test_half_drift_fanger_reel_udtraetning():
    assert _half_drift([255, 256, 265, 266]) == 10


def test_pace_str():
    assert _pace_str(252.4) == '4:12'
    assert _pace_str(None) == '-'


def test_count_planned_reps_fra_workout_doc():
    ev = {'workout_doc': {'steps': [
        {'text': 'Varm-op'},
        {'reps': 4, 'steps': [{'text': 'Interval'}, {'text': 'Pause'}]},
        {'text': 'Cool-down'},
    ]}}
    assert count_planned_reps(ev) == 4


def test_count_planned_reps_fra_navn():
    assert count_planned_reps({'name': 'Løb VO2 4×5 min Z4-Z5'}) == 4
    assert count_planned_reps({'name': 'Cykel 5x3 min Z4'}) == 5


def test_count_planned_reps_ukendt_giver_none():
    assert count_planned_reps({'name': 'Løb Z2 45 min'}) is None
    assert count_planned_reps({}) is None


# ── Target læses fra workout_doc, ikke fra navnet ────────────────────────────

VO2_EVENT = {
    'name': 'Løb VO2 4×5 min Z4-Z5',
    'workout_doc': {'steps': [
        {'text': 'Varm-op', 'duration': 900,
         'pace': {'start': 65, 'end': 78, 'units': '%pace'}},
        {'reps': 4, 'text': '4x', 'steps': [
            {'text': 'Interval 4:17-4:29/km', 'duration': 300,
             'pace': {'start': 98, 'end': 103, 'units': '%pace'}},
            {'text': 'Pause', 'duration': 180,
             'pace': {'start': 65, 'end': 78, 'units': '%pace'}},
        ]},
        {'text': 'Cool-down', 'duration': 600,
         'pace': {'start': 65, 'end': 78, 'units': '%pace'}},
    ]},
}


def test_target_laeses_fra_workout_doc_ikke_navnet():
    # Navnet siger Z4-Z5, men de faktiske trin er 98-103% = 4:17-4:29 (Z4)
    assert planned_target_from_event(VO2_EVENT, 'run') == (257, 269)


def test_target_vaelger_arbejdstrin_ikke_pause():
    lo, hi = planned_target_from_event(VO2_EVENT, 'run')
    assert lo < 300 and hi < 300      # pausen (65-78%) ville give 338+ sek/km


def test_navnebaseret_zone_ville_have_doemt_forkert():
    """Regression: Z5-bånd på et Z4-pas vender verdikten på hovedet."""
    iv = load_fixture()
    korrekt = get_interval_reps('x', 'Z5', 'run', streams={}, intervals=iv,
                                target=planned_target_from_event(VO2_EVENT, 'run'))
    forkert = get_interval_reps('x', 'Z5', 'run', streams={}, intervals=iv)
    assert [r['flag'] for r in korrekt] == ['fast', 'ok', 'fast', 'ok']
    assert [r['flag'] for r in forkert] == ['ok', 'slow', 'ok', 'slow']


def test_target_uden_workout_doc_giver_none():
    assert planned_target_from_event({'name': 'Løb Z4'}, 'run') == (None, None)
    assert planned_target_from_event({}, 'run') == (None, None)


def test_bike_target_fra_workout_doc():
    ev = {'workout_doc': {'steps': [
        {'reps': 5, 'steps': [
            {'power': {'start': 91, 'end': 100, 'units': '%ftp'}, 'duration': 180},
            {'power': {'start': 44, 'end': 56, 'units': '%ftp'}, 'duration': 240},
        ]},
    ]}}
    assert planned_target_from_event(ev, 'bike') == (253, 278)


# ── Trigger: struktur, ikke zonenavn ─────────────────────────────────────────

def test_trigger_paa_workout_doc_gruppe():
    from modules.sessions import has_rep_structure
    assert has_rep_structure(VO2_EVENT, 'run') is True


def test_trigger_fanger_z3_intervalpas():
    """Regression: 'Hometrainer 3×15 min Z3' fik aldrig rep-analyse."""
    from modules.sessions import has_rep_structure
    ev = {'name': 'Hometrainer 3×15 min Z3', 'workout_doc': {'steps': [
        {'text': 'Varm-op', 'duration': 600},
        {'reps': 3, 'steps': [
            {'power': {'start': 76, 'end': 91, 'units': '%ftp'}, 'duration': 900},
            {'power': {'start': 56, 'end': 70, 'units': '%ftp'}, 'duration': 300},
        ]},
    ]}}
    assert has_rep_structure(ev, 'bike') is True


def test_navn_alene_trigger_ikke():
    """Uden workout_doc kender vi hverken varighed eller target."""
    from modules.sessions import has_rep_structure
    assert has_rep_structure({'name': 'Løb VO2 4×5 min Z4'}, 'run') is False


def test_kontinuerlige_pas_trigger_ikke():
    from modules.sessions import has_rep_structure
    assert has_rep_structure({'name': 'Løb Z2 29 km langt'}, 'run') is False
    assert has_rep_structure({'name': 'Cykel Z2 3 timer', 'workout_doc':
                              {'steps': [{'text': 'Z2', 'duration': 10800}]}}, 'bike') is False
    assert has_rep_structure({}, 'run') is False


def test_enkelt_rep_trigger_ikke():
    from modules.sessions import has_rep_structure
    ev = {'workout_doc': {'steps': [{'reps': 1, 'steps': [
        {'pace': {'start': 98, 'end': 103, 'units': '%pace'}, 'duration': 1200}]}]}}
    assert has_rep_structure(ev, 'run') is False


def test_strides_trigger_ikke():
    """20-sekunders strides kan ikke pace-vurderes — GPS-støj > signal."""
    from modules.sessions import has_rep_structure
    ev = {'name': 'Shakeout løb + strides', 'workout_doc': {'steps': [
        {'text': 'Let løb', 'duration': 600,
         'pace': {'start': 65, 'end': 78, 'units': '%pace'}},
        {'reps': 4, 'steps': [
            {'text': 'Stride 20s', 'duration': 20,
             'pace': {'start': 103, 'end': 112, 'units': '%pace'}},
            {'text': 'Jog 40s', 'duration': 40,
             'pace': {'start': 65, 'end': 78, 'units': '%pace'}}]}]}}
    assert has_rep_structure(ev, 'run') is False


def test_et_minut_reps_trigger_ikke():
    """6×1 min race-pace: arbejde 5:00-5:38 og jog >5:39 kan ikke skilles."""
    from modules.sessions import has_rep_structure
    ev = {'name': 'Løb Z2 40 min + 6×1 min race-pace', 'workout_doc': {'steps': [
        {'reps': 6, 'steps': [
            {'text': 'Race-pace 1 min', 'duration': 60,
             'pace': {'start': 78, 'end': 88, 'units': '%pace'}},
            {'text': 'Jog', 'duration': 60,
             'pace': {'start': 65, 'end': 78, 'units': '%pace'}}]}]}}
    assert has_rep_structure(ev, 'run') is False


def test_hometrainer_z3_trigger():
    """Regression: intervalpas i Z3 blev tidligere aldrig analyseret."""
    from modules.sessions import interval_spec
    ev = {'name': 'Hometrainer 3×15 min Z3 90 min', 'workout_doc': {'steps': [
        {'ramp': True, 'warmup': True, 'duration': 900,
         'power': {'start': 50, 'end': 76, 'units': '%ftp'}},
        {'reps': 3, 'steps': [
            {'text': 'Z3 interval', 'duration': 900,
             'power': {'start': 76, 'end': 91, 'units': '%ftp'}},
            {'text': 'Pause', 'duration': 300,
             'power': {'start': 56, 'end': 76, 'units': '%ftp'}}]}]}}
    spec = interval_spec(ev, 'bike')
    assert spec['reps'] == 3 and spec['work_secs'] == 900
    assert spec['target'] == (211, 253)


def test_merged_pauser_kasseres():
    """Hvis pauserne ryger med i repsene, må analysen ikke bruges."""
    spec = {'reps': 3, 'work_secs': 300, 'target': (257, 269), 'rest': (275, 300)}
    # Alt ligger tæt på target -> ét langt blob på 1500s = 5x det planlagte
    iv = [mk(1500, 265)]
    assert get_interval_reps('x', 'Z4', 'run', streams={}, intervals=iv,
                             target=(257, 269), spec=spec) == []


def test_skillelinje_bruger_pausens_target():
    """Pausen skal falde uden for arbejdet, også når båndene ligger tæt."""
    spec = {'reps': 2, 'work_secs': 300, 'target': (257, 269), 'rest': (290, 340)}
    iv = [mk(300, 262), mk(180, 300), mk(300, 264)]
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=iv,
                             target=(257, 269), spec=spec)
    assert len(reps) == 2


def test_fragment_taeller_ikke_som_rep():
    """En afbrudt rep på under halvdelen af planlagt tid er ikke gennemført."""
    spec = {'reps': 3, 'work_secs': 300, 'target': (257, 269), 'rest': (339, 406)}
    iv = [mk(300, 262), mk(180, 350), mk(80, 261), mk(180, 350), mk(299, 263)]
    reps = get_interval_reps('x', 'Z4', 'run', streams={}, intervals=iv,
                             target=(257, 269), spec=spec)
    assert len(reps) == 2
