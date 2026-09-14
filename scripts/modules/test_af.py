"""Tests for AF-modulet — klynge-detektion af sammenhængende drikkedage."""
from datetime import date, timedelta

from .af import detect_alcohol_cluster


TODAY = date(2026, 8, 9)


def _log(pattern, today=TODAY):
    """pattern: liste af 0/1/None, index 0 = i dag, 1 = i går, osv."""
    out = {}
    for offset, val in enumerate(pattern):
        if val is not None:
            out[str(today - timedelta(days=offset))] = val
    return out


def test_ingen_log_giver_none():
    assert detect_alcohol_cluster({}) is None
    assert detect_alcohol_cluster(None) is None


def test_enkelt_drikkedag_udloeser_ikke():
    assert detect_alcohol_cluster(_log([0, 1, 0, 0, 0, 0, 0]), today=TODAY) is None


def test_spredte_drikkedage_udloeser_ikke():
    assert detect_alcohol_cluster(_log([1, 0, 1, 0, 1, 0, 0]), today=TODAY) is None


def test_to_i_traek_findes():
    c = detect_alcohol_cluster(_log([0, 1, 1, 0, 0, 0, 0]), today=TODAY)
    assert c == {'days': 2, 'start': '2026-08-07', 'end': '2026-08-08'}


def test_tre_i_traek_findes_med_korrekt_span():
    c = detect_alcohol_cluster(_log([0, 0, 1, 1, 1, 0, 0]), today=TODAY)
    assert c['days'] == 3
    assert c['start'] == '2026-08-05'
    assert c['end'] == '2026-08-07'


def test_klynge_der_slutter_i_dag():
    c = detect_alcohol_cluster(_log([1, 1, 0, 0, 0, 0, 0]), today=TODAY)
    assert c == {'days': 2, 'start': '2026-08-08', 'end': '2026-08-09'}


def test_laengste_klynge_vinder():
    c = detect_alcohol_cluster(_log([1, 1, 0, 1, 1, 1, 0]), today=TODAY)
    assert c['days'] == 3
    assert c['end'] == '2026-08-06'


def test_uregistreret_dag_bryder_raekken():
    c = detect_alcohol_cluster(_log([1, None, 1, 0, 0, 0, 0]), today=TODAY)
    assert c is None


def test_klynge_uden_for_vinduet_ignoreres():
    # Drikkedage 8-9 dage tilbage ligger uden for 7-dages vinduet
    pattern = [0] * 7 + [1, 1]
    assert detect_alcohol_cluster(_log(pattern), today=TODAY) is None


def test_klynge_der_krydser_vinduekanten_taeller_kun_indenfor():
    # 1'ere på offset 5,6,7 — kun 5 og 6 er inde i 7-dages vinduet
    pattern = [0, 0, 0, 0, 0, 1, 1, 1]
    c = detect_alcohol_cluster(_log(pattern), today=TODAY)
    assert c['days'] == 2


def test_min_run_kan_haeves():
    assert detect_alcohol_cluster(_log([0, 1, 1, 0, 0, 0, 0]),
                                  min_run=3, today=TODAY) is None


def test_vindue_kan_udvides():
    pattern = [0] * 7 + [1, 1]
    c = detect_alcohol_cluster(_log(pattern), window_days=14, today=TODAY)
    assert c['days'] == 2


def test_af_dage_alene_giver_none():
    assert detect_alcohol_cluster(_log([0] * 7), today=TODAY) is None


def test_af_history_12_weeks_with_monday(monkeypatch):
    """14/9-2026: historik går 12 uger tilbage uanset programstart og bærer
    `monday`, som frontend bruger til dag-opslag i af_log."""
    from . import af
    class R:
        status_code = 200
        def json(self):
            return []
    monkeypatch.setattr(af, 'api_get', lambda *a, **k: R())
    h = af.get_af_history()
    assert len(h) <= 12 and h[-1]['total'] >= 1
    assert all('monday' in w and w['monday'].endswith(('1','2','3','4','5','6','7','8','9','0')) for w in h)
    from datetime import date
    assert all(date.fromisoformat(w['monday']).weekday() == 0 for w in h)
    assert [w['monday'] for w in h] == sorted(w['monday'] for w in h)
