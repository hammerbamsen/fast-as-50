"""Tests for check-in-modulet (protein/energi/aftensult-historik)."""
from datetime import date, timedelta

from .checkin import (build_checkin_log, protein_days, protein_weekly_avg,
                      protein_kpi, energy_avg, hunger_days, af_kinds, coach_line)

TODAY = date(2026, 9, 4)


def _rows(spec):
    """spec: {offset: {felt: værdi}} — offset 0 = i dag."""
    out = []
    for offset, fields in spec.items():
        row = {'id': str(TODAY - timedelta(days=offset))}
        row.update(fields)
        out.append(row)
    return out


def test_log_har_28_dage_aeldst_foerst_og_huller_er_none():
    log = build_checkin_log(_rows({0: {'protein': 2}}), today=TODAY)
    assert len(log) == 28
    assert log[0]['date'] == str(TODAY - timedelta(days=27))
    assert log[-1] == {'date': '2026-09-04', 'alkohol': None, 'protein': 2, 'energi': None, 'sult': None}
    assert log[-2]['protein'] is None


def test_felter_mappes_fra_intervals_navne():
    rows = _rows({0: {'Alkohol': 2, 'protein': 1, 'motivation': 4.0, 'Aftensult': 1}})
    e = build_checkin_log(rows, today=TODAY)[-1]
    assert e == {'date': '2026-09-04', 'alkohol': 2, 'protein': 1, 'energi': 4, 'sult': 1}


def test_protein_dage_og_ugesnit():
    spec = {i: {'protein': 2} for i in range(0, 5)}        # 5 dage 3/3 denne uge
    spec.update({i: {'protein': 1} for i in range(5, 7)})
    spec.update({i: {'protein': 2} for i in range(7, 10)}) # 3 dage ugen før
    log = build_checkin_log(_rows(spec), today=TODAY)
    assert protein_days(log, 7) == 5
    # 28 dage = 4 uger: 5 + 3 + 0 + 0 = 8 / 4
    assert protein_weekly_avg(log) == 2.0


def test_protein_kpi_farve_og_sub():
    log = build_checkin_log(_rows({i: {'protein': 2} for i in range(6)}), today=TODAY)
    k = protein_kpi(log)
    assert k['value'] == '6' and k['unit'] == '/7'
    assert k['sub'].startswith('3/3-dage · 4 uger 1,5')
    assert k['color'] == '#27AE60'
    assert protein_kpi(build_checkin_log([], today=TODAY))['color'] == '#7A6A58'
    lav = build_checkin_log(_rows({0: {'protein': 0}, 1: {'protein': 1}}), today=TODAY)
    assert protein_kpi(lav)['color'] == '#C0392B'


def test_energi_snit_ignorerer_uregistrerede():
    log = build_checkin_log(_rows({0: {'motivation': 4}, 1: {'motivation': 3}, 9: {'motivation': 1}}), today=TODAY)
    assert energy_avg(log, 7) == 3.5
    assert energy_avg(build_checkin_log([], today=TODAY)) is None


def test_aftensult_taeller_kun_ja():
    log = build_checkin_log(_rows({0: {'Aftensult': 2}, 1: {'Aftensult': 1}, 2: {'Aftensult': 2}}), today=TODAY)
    assert hunger_days(log, 7) == 2


def test_af_kinds_kun_for_drikkedage():
    log = build_checkin_log(_rows({0: {'Alkohol': 0}, 1: {'Alkohol': 1}, 2: {'Alkohol': 2}}), today=TODAY)
    assert af_kinds(log) == {'2026-09-03': 'drak', '2026-09-02': 'drak'}   # før KIND_CUTOVER = 'drak'


def test_af_kinds_efter_cutover():
    log = [{'date': '2026-09-10', 'alkohol': 1}, {'date': '2026-09-11', 'alkohol': 2}, {'date': '2026-09-12', 'alkohol': 0}]
    assert af_kinds(log) == {'2026-09-10': 'faa', '2026-09-11': 'mange'}


def test_coach_line():
    assert coach_line(build_checkin_log([], today=TODAY)) is None
    log = build_checkin_log(_rows({0: {'protein': 2, 'motivation': 3, 'Aftensult': 2},
                                   1: {'protein': 2, 'motivation': 4}}), today=TODAY)
    assert coach_line(log) == 'Protein 3/3-dage sidste 7: 2 · aftensult-dage: 1 · energi-snit: 3,5'
