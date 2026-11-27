# -*- coding: utf-8 -*-
"""Tests for fixed_route — EF paa fast rute (27/11-2026)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import fixed_route as fr


def _streams(segments):
    """segments = [(sekunder, meter, hoejdemeter, watt, puls)] lagt i forlaengelse.
    1 sample pr. sekund, som Intervals leverer."""
    time, dist, alt, watts, hr = [], [], [], [], []
    t = d = a = 0
    for secs, meter, hm, w, h in segments:
        for i in range(secs):
            t += 1
            d += meter / secs
            a += hm / secs
            time.append(t); dist.append(round(d, 1)); alt.append(round(a, 1))
            watts.append(w); hr.append(h)
    return [{"type": "time", "data": time}, {"type": "distance", "data": dist},
            {"type": "altitude", "data": alt}, {"type": "watts", "data": watts},
            {"type": "heartrate", "data": hr}]


# tilkoersel 20 min flad, Sa Calobra 36 min, nedkoersel 15 min
SA_CALOBRA = [(1200, 12000, 40, 180, 130),
              (2160, 9450, 627, 275, 150),
              (900, 9400, -620, 120, 120)]


def test_finder_stigningen_i_en_hel_tur():
    """Vinduet skal ramme stigningen, ikke tilkoerslen: 9,45 km / 627 hm / 36 min."""
    e = fr.find_effort(_streams(SA_CALOBRA))
    assert e is not None
    assert abs(e["secs"] - 2160) <= 30        # 36 min +/- et halvt minut
    assert abs(e["km"] - 9.45) <= 0.2
    assert abs(e["hm"] - 627) <= 20
    assert e["watts"] == 275 and e["hr"] == 150
    # EF regnes paa de uafrundede gennemsnit, saa den maa afvige lidt fra 275/150
    assert abs(e["ef"] - 275 / 150) < 0.01


def test_en_flad_tur_giver_ingen_stigning():
    flad = [(3600, 30000, 120, 200, 135)]
    assert fr.find_effort(_streams(flad)) is None


def test_en_anden_stigning_matcher_ikke_ruten():
    # Puig Major: 14 km / 800 hm — uden for begge tolerancer
    anden = [(600, 6000, 20, 180, 128), (3000, 14000, 800, 260, 148)]
    assert fr.find_effort(_streams(anden)) is None
    # og en for kort stigning
    kort = [(600, 6000, 20, 180, 128), (1200, 5000, 400, 280, 152)]
    assert fr.find_effort(_streams(kort)) is None


def test_vaelger_stigningen_og_ikke_stigning_plus_pause():
    # samme stigning koert med en pause paa 10 min i midten
    pause = [(600, 6000, 20, 170, 125),
             (1000, 4700, 310, 280, 152),
             (600, 50, 2, 0, 110),
             (1100, 4750, 317, 270, 155)]
    e = fr.find_effort(_streams(pause))
    assert e is not None
    # vinduet maa daekke hele stigningen inkl. pausen — men den lavere
    # gennemsnitswatt skal slaa igennem, saa EF ikke ser bedre ud end den var
    assert e["watts"] < 275


def test_manglende_puls_eller_watt_giver_ingen_ef():
    st = fr.find_effort([{"type": "distance", "data": [i * 10.0 for i in range(1000)]},
                         {"type": "altitude", "data": [i * 0.7 for i in range(1000)]}])
    assert st is not None and st["ef"] is None and st["watts"] is None


def test_for_lidt_data():
    assert fr.find_effort([{"type": "distance", "data": [1, 2, 3]}]) is None
    assert fr.find_effort([]) is None
    assert fr.find_effort(None) is None
    assert fr.find_effort(_streams(SA_CALOBRA), route="findes-ikke") is None


def test_forfilter_sparer_stream_kald():
    bike = ("Ride", "GravelRide")
    assert fr.is_candidate({"type": "Ride", "total_elevation_gain": 1400}, bike)
    assert not fr.is_candidate({"type": "Ride", "total_elevation_gain": 120}, bike)
    assert not fr.is_candidate({"type": "Run", "total_elevation_gain": 1400}, bike)
    assert fr.is_candidate({"type": "Ride", "icu_elevation_gain": 900}, bike)


def test_merge_laver_ingen_dubletter():
    a = {"id": 1, "date": "2027-03-16", "ef": 1.8, "route": "sa_calobra"}
    b = {"id": 2, "date": "2027-04-13", "ef": 1.9, "route": "sa_calobra"}
    a2 = {"id": 1, "date": "2027-03-16", "ef": 1.85, "route": "sa_calobra"}
    s = fr.merge([a], [b])
    assert [r["id"] for r in s] == [1, 2]
    s2 = fr.merge(s, [a2])                   # samme id igen -> opdateres
    assert [r["id"] for r in s2] == [1, 2] and s2[0]["ef"] == 1.85


def test_card_retning():
    def row(i, d, ef, secs=2160):
        return {"id": i, "date": d, "ef": ef, "secs": secs, "route": "sa_calobra"}
    tom = fr.card([])
    assert tom["n"] == 0 and tom["status"] == "ingen forsøg endnu"
    ett = fr.card([row(1, "2027-03-16", 1.80)])
    assert ett["status"] == "første forsøg — ingen retning endnu" and ett["ef"] == 1.80
    bedre = fr.card([row(1, "2027-03-16", 1.80), row(2, "2027-04-13", 1.90)])
    assert bedre["color"] == "#27AE60" and bedre["pct"] == 5.6
    daarligere = fr.card([row(1, "2027-03-16", 1.80), row(2, "2027-04-13", 1.70)])
    assert daarligere["color"] == "#C0392B" and daarligere["pct"] == -5.6
    stoej = fr.card([row(1, "2027-03-16", 1.80), row(2, "2027-04-13", 1.81)])
    assert stoej["color"] == "#F39C12" and "støjen" in stoej["status"]
    # bedste tid foelger med, saa PR'en kan staa ved siden af EF
    tider = fr.card([row(1, "2027-03-16", 1.8, 2200), row(2, "2027-04-13", 1.9, 2100)])
    assert tider["best_secs"] == 2100
