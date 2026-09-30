# -*- coding: utf-8 -*-
"""Tests for sessions.py — distance-bevidst completion (rettet 7/8-2026).

Rodårsag: en session med et eksplicit meter-mål (typisk svøm) kunne fremstå
'done' udelukkende ud fra TSS/tid, selvom den faktiske distance lå markant
under planen — fordi 1) distance slet ikke indgik i calc_completion, og
2) planned_tss/planned_mins reelt aldrig blev lagt på session-objektet i
get_planned_weeks(), så completion typisk faldt tilbage til "ingen data,
antag done". Sagen der udløste rettelsen: 7/8-2026, OW-svøm planlagt 2500m/
50 min/45 TSS, realiseret 1390m/33 min/33 TSS — coachen nævnte intet om
distancen, fordi den aldrig blev sammenlignet.
"""
from datetime import date

from . import sessions

TODAY_KEY = sessions.DAY_SHORT[date.today().weekday()]


# ── parse_planned_distance_m ────────────────────────────────────────────

def test_parse_distance_simple():
    assert sessions.parse_planned_distance_m("Svøm 2000m teknisk") == 2000


def test_parse_distance_with_surrounding_text():
    assert sessions.parse_planned_distance_m(
        "OW-svøm 2500m SAMMENHÆNGENDE (Christiansborg-generalprøve)") == 2500


def test_parse_distance_range_uses_upper_bound():
    assert sessions.parse_planned_distance_m("OW-svøm 800-1500m") == 1500


def test_parse_distance_ignores_minutes():
    assert sessions.parse_planned_distance_m("OW-svøm Open water 40 min") is None
    assert sessions.parse_planned_distance_m("Svøm let 30 min recovery") is None


def test_parse_distance_reads_km_but_ignores_hm():
    """Ændret 8/8-2026. Tidligere blev km bevidst ignoreret, fordi funktionen
    kun skulle dække svøm i meter. Konsekvensen var at løb og cykel ALDRIG fik
    et distance-mål, og coach-prompten citerede derfor plantallet fra label'en
    som udført distance — 28,2 km løbet blev refereret som '29 km'.
    Højdemeter (hm) skal fortsat IKKE opfattes som distance."""
    assert sessions.parse_planned_distance_m(
        "Løb Fornalutx – Far des Cap Gros loop, 21,28 km / 502 hm") == 21280
    assert sessions.parse_planned_distance_m("Cykel bjergpas 1200 hm") is None
    assert sessions.parse_planned_distance_m("Cykel bjergpas 1200hm") is None


def test_parse_distance_km_variants():
    assert sessions.parse_planned_distance_m("Lang løb Z2 29 km (155 min)") == 29000
    assert sessions.parse_planned_distance_m("Cykel Formentor 149km") == 149000
    assert sessions.parse_planned_distance_m("Løb 28-30 km marathon-ladder") == 30000


def test_parse_distance_km_takes_priority_over_minutes():
    """'155 min' må aldrig blive til et distance-mål, og km-grenen må ikke
    lade meter-grenen snuppe et tilfældigt 3-cifret tal i samme label."""
    assert sessions.parse_planned_distance_m("Lang løb Z2 32 km (170 min)") == 32000
    assert sessions.parse_planned_distance_m("Løb Z1 30 min let") is None


def test_compliance_prompt_line_shows_actual_distance():
    """Regressionsvagt for selve fejlen: prompt-linjen skal vise den FAKTISKE
    distance, ikke kun planens label."""
    line = sessions.format_compliance_for_prompt([{
        'day': 'Lør', 'label': 'Lang løb Z2 29 km', 'zone_flag': 'ok',
        'note': '66% i Z2 (pace) — on target',
        'moving_mins': 147, 'planned_mins': 155,
        'distance_m': 28227.0, 'planned_distance_m': 29000,
    }])
    assert '28,2/29,0 km' in line
    assert '147/155 min' in line


def test_parse_distance_no_match_returns_none():
    assert sessions.parse_planned_distance_m("Styrke A") is None
    assert sessions.parse_planned_distance_m("") is None
    assert sessions.parse_planned_distance_m(None) is None


# ── calc_completion — distance som ekstra dimension ─────────────────────

def test_completion_distance_shortfall_overrides_ok_time():
    """Dagens faktiske sag (7/8-2026): TSS/tid ser fint ud (73%/66%), men
    distancen (56%) er det svageste mål og skal afgøre status."""
    status, pct = sessions.calc_completion(
        actual_tss=33, planned_tss=45, actual_mins=33, planned_mins=50,
        actual_distance_m=1390, planned_distance_m=2500,
    )
    assert status == "partial"
    assert pct == 56


def test_completion_distance_met_stays_done():
    status, pct = sessions.calc_completion(
        actual_tss=45, planned_tss=45, actual_mins=50, planned_mins=50,
        actual_distance_m=2600, planned_distance_m=2500,
    )
    assert status == "done"


def test_completion_missing_distance_data_not_penalized():
    """Garmin/Intervals har ikke rapporteret distance for aktiviteten ->
    distance-kandidaten skal IGNORERES, ikke tælle som 0m (falsk 'minimal')."""
    status, pct = sessions.calc_completion(
        actual_tss=40, planned_tss=45, actual_mins=None, planned_mins=None,
        actual_distance_m=None, planned_distance_m=2500,
    )
    assert status == "done"  # 40/45 = 89% -- distance udelades pga. manglende data


def test_completion_no_distance_target_unchanged_behavior():
    """Ingen distance-mål i planen -> identisk med adfærden før rettelsen."""
    status, pct = sessions.calc_completion(
        actual_tss=35, planned_tss=70, actual_mins=None, planned_mins=None,
    )
    assert status == "partial"
    assert pct == 50


def test_completion_total_data_gap_still_assumes_done():
    assert sessions.calc_completion(None, None, None, None) == ("done", None)


# ── build_week_sessions — fuld pipeline med mock Intervals-data ─────────

def test_build_week_sessions_flags_todays_swim_shortfall():
    planned = [{
        "day": TODAY_KEY, "disc": "openwater",
        "label": "OW-svøm 2500m SAMMENHÆNGENDE (Christiansborg-generalprøve)",
        "done": False, "today": True,
        "planned_tss": 45, "planned_mins": 50, "planned_distance_m": 2500,
    }]
    done_map = {
        TODAY_KEY: [("openwater", "Gentofte Svømning i åbent vand", 33, 33,
                      None, None, None, None, "act123", 1390)]
    }
    result = sessions.build_week_sessions(done_map, planned)
    today = next(s for s in result if s.get("today"))
    assert today["completion"] == "partial"
    assert today["completion_pct"] == 56
    assert today["actual_distance_m"] == 1390
    assert today["planned_distance_m"] == 2500
    assert today["done"] is True  # partial tæller stadig som "forsøgt" (uændret semantik)


def test_build_week_sessions_no_distance_target_unaffected():
    """Regression: pas uden meter-mål i planen (fx cykel) skal opføre sig
    som før — ingen distance-felter, ren TSS/tid-vurdering."""
    planned = [{
        "day": TODAY_KEY, "disc": "bike", "label": "Cykel Z2 90 min",
        "done": False, "today": True,
        "planned_tss": None, "planned_mins": None, "planned_distance_m": None,
    }]
    done_map = {
        TODAY_KEY: [("bike", "Morgentur", 68, 88, None, None, None, None, "act456", None)]
    }
    result = sessions.build_week_sessions(done_map, planned)
    today = next(s for s in result if s.get("today"))
    assert today["completion"] == "done"
    assert today.get("actual_distance_m") is None
    assert today.get("planned_distance_m") is None


def test_build_week_sessions_carries_activity_name():
    """30/9-2026: aktivitetens Garmin-navn (med stednavn) lægges på passet som
    actual_name, så dashboardet kan se at en cykeltur er kørt fra Fornalutx."""
    planned = [{
        "day": TODAY_KEY, "disc": "bike", "label": "Cykel Z2 240 min",
        "done": False, "today": True,
        "planned_tss": 171, "planned_mins": 240, "planned_distance_m": None,
    }]
    done_map = {
        TODAY_KEY: [("bike", "Fornalutx Cykling på vej", 95, 300, None, None, None, None, "act789", None)]
    }
    result = sessions.build_week_sessions(done_map, planned)
    today = next(s for s in result if s.get("today"))
    assert today["actual_name"] == "Fornalutx Cykling på vej"


# ── calc_completion — hike/walk måles på tid, ikke TSS (13/8-2026) ──────

def test_hike_uses_duration_not_tss():
    """Torsdag 13/8-2026: 90 af 120 planlagte min = 75%, men kun 14 af 76 TSS
    = 18% -> blev stemplet 'minimal' og dermed ikke markeret gennemført."""
    status, pct = sessions.calc_completion(
        actual_tss=14, planned_tss=76, actual_mins=90, planned_mins=120,
        disc="hike",
    )
    assert status == "partial"
    assert pct == 75


def test_hike_full_duration_is_done():
    status, pct = sessions.calc_completion(
        actual_tss=60, planned_tss=114, actual_mins=174, planned_mins=180,
        disc="hike",
    )
    assert status == "done"
    assert pct == 97


def test_hike_genuinely_short_still_minimal():
    """Varighed-først må ikke gøre alle hikes grønne: 20 af 120 min = 17%."""
    status, pct = sessions.calc_completion(
        actual_tss=4, planned_tss=76, actual_mins=20, planned_mins=120,
        disc="hike",
    )
    assert status == "minimal"


def test_strength_uses_duration_not_tss():
    """3/9-2026: styrke 42 af 45 min men 6 af 40 TSS -> skal være done, ikke minimal."""
    status, pct = sessions.calc_completion(
        actual_tss=6, planned_tss=40, actual_mins=42, planned_mins=45,
        disc="strength",
    )
    assert status == "done"
    assert pct == 93


def test_strength_short_is_still_partial():
    status, pct = sessions.calc_completion(
        actual_tss=3, planned_tss=40, actual_mins=25, planned_mins=45,
        disc="strength",
    )
    assert status == "partial"
    assert pct == 56


def test_hike_without_duration_data_falls_back_to_tss():
    status, pct = sessions.calc_completion(
        actual_tss=70, planned_tss=76, actual_mins=None, planned_mins=None,
        disc="hike",
    )
    assert status == "done"


def test_run_still_uses_tss_not_duration():
    """Regression: løb/cykel må IKKE skifte til varighed-først. Et løb der
    rammer tiden men ikke intensiteten skal stadig flages."""
    status, pct = sessions.calc_completion(
        actual_tss=20, planned_tss=87, actual_mins=95, planned_mins=95,
        disc="run",
    )
    assert status == "partial"
    assert pct == 23


def test_hike_distance_target_still_counts():
    """Varighed-først erstatter kun TSS-kandidaten — et eksplicit distance-mål
    indgår stadig som svageste led."""
    status, pct = sessions.calc_completion(
        actual_tss=14, planned_tss=76, actual_mins=110, planned_mins=120,
        actual_distance_m=4000, planned_distance_m=10000, disc="hike",
    )
    assert status == "partial"
    assert pct == 40
