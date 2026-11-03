# -*- coding: utf-8 -*-
"""Tests for kælder-cykelbiblioteket."""
import xml.etree.ElementTree as ET

import pytest

from . import bike_library as B

ALL = B.ids()


def test_biblioteket_er_ikke_tomt():
    assert len(ALL) >= 15
    assert len(set(ALL)) == len(ALL), "duplikerede id'er"


def test_alle_har_paakraevede_felter():
    for w in B.all_workouts():
        for f in ("id", "name", "category", "load", "purpose", "steps", "est_min"):
            assert w.get(f) not in (None, "", []), "%s mangler %s" % (w["id"], f)
        assert w["load"] in ("let", "moderat", "haard")
        assert w["category"] in B.meta()["categories"]


def test_navne_er_unikke():
    names = [w["name"] for w in B.all_workouts()]
    assert len(set(names)) == len(names)


@pytest.mark.parametrize("wid", ALL)
def test_zwo_er_gyldig_xml(wid):
    root = ET.fromstring(B.to_zwo(wid))
    assert root.tag == "workout_file"
    assert root.findtext("name")
    assert root.find("workout") is not None
    assert len(root.find("workout")) > 0


@pytest.mark.parametrize("wid", ALL)
def test_zwo_effekt_er_i_rimeligt_interval(wid):
    """Ingen step under 25% eller over 200% FTP — fanger komma- og faktorfejl."""
    root = ET.fromstring(B.to_zwo(wid))
    for el in root.find("workout").iter():
        for attr in ("Power", "PowerLow", "PowerHigh", "OnPower", "OffPower"):
            if attr in el.attrib:
                v = float(el.attrib[attr])
                assert 0.25 <= v <= 2.0, "%s: %s=%s" % (wid, attr, v)


@pytest.mark.parametrize("wid", ALL)
def test_intervals_doc_har_steps_og_varighed(wid):
    iv = B.to_intervals(wid)
    assert iv["type"] == "Ride"
    assert iv["workout_doc"]["steps"]
    assert iv["moving_time"] == B.duration_seconds(wid)
    # 3/11-2026: rene opvarmningspas (tag "opvarmning", fx før Zwift Video) må være korte
    min_s = 10 * 60 if "opvarmning" in (B.get(wid).get("tags") or []) else 20 * 60
    assert iv["moving_time"] > min_s


@pytest.mark.parametrize("wid", ALL)
def test_est_min_matcher_faktisk_varighed(wid):
    """est_min er genereret, ikke håndskrevet — den må ikke drifte."""
    assert B.get(wid)["est_min"] == B.duration_seconds(wid) // 60


@pytest.mark.parametrize("wid", ALL)
def test_erg_false_er_dokumenteret(wid):
    w = B.get(wid)
    if not w.get("erg", True):
        assert "ERG" in B.to_intervals(wid)["description"]
        assert "ERG" in B.to_zwo(wid)


def test_zwo_filnavne_er_unikke_og_ascii():
    fns = [B.zwo_filename(i) for i in ALL]
    assert len(set(fns)) == len(fns)
    for f in fns:
        f.encode("ascii")  # rejser hvis æøå slap igennem
        assert f.endswith(".zwo")
        assert " " not in f


def test_check_week_godkender_lovlig_uge():
    assert B.check_week(["vo2_5x3", "tae_2x20", "z2_grundtur_80"]) == []


def test_check_week_fanger_for_mange_haarde():
    warn = B.check_week(["vo2_5x3", "tae_2x20", "tae_3x12"])
    assert warn and "hårde pas" in warn[0]


def test_check_week_fanger_for_mange_moderate():
    warn = B.check_week(["ss_3x15", "dur_bjergtur_3t", "bjerg_tds_2x45"])
    assert any("moderate" in w for w in warn)


def test_lav_glykogen_flages_sammen_med_haardt():
    warn = B.check_week(["dur_lav_glykogen", "vo2_5x3"])
    assert any("lav glykogen" in w for w in warn)


def test_ukendt_id_rejser():
    with pytest.raises(KeyError):
        B.get("findes_ikke")


def test_der_er_mindst_et_durability_pas():
    """Durability er den faktiske limiter for Ultrafondo — biblioteket skal dække den."""
    assert len(B.by_category("durability")) >= 3


def test_sweetspot_er_begraenset():
    """Bevidst: evidensen bærer ikke sweet spot som rygrad. Max ét pas."""
    assert len(B.by_category("sweetspot")) <= 1


def test_ingen_ekstrem_lav_kadence():
    """Frontiers 2014: 40 rpm hos veteraner gav ingen effekt. Under 65 rpm er folklore."""
    for w in B.all_workouts():
        for s in _flat(w["steps"]):
            if s.get("cad"):
                assert s["cad"] >= 65, "%s har %d rpm" % (w["id"], s["cad"])


def _flat(steps):
    for s in steps:
        if s["type"] == "reps":
            for x in _flat(s["steps"]):
                yield x
        else:
            yield s


# ── integration med søndagscheck-in ─────────────────────────────
def test_katalog_kun_paa_soendag():
    from . import coach
    assert coach.build_bike_library_line(0) == ""
    assert coach.build_bike_library_line(5) == ""
    assert "KAELDER-KATALOG" in coach.build_bike_library_line(6)


def test_katalog_indeholder_alle_id_er():
    from . import coach
    line = coach.build_bike_library_line(6)
    for wid in ALL:
        assert wid in line, "%s mangler i søndagsprompten" % wid


def test_katalog_advarer_ved_ulovlig_uge():
    from . import coach
    line = coach.build_bike_library_line(6, ["vo2_5x3", "tae_2x20", "tae_3x12"])
    assert "ADVARSEL" in line


def test_katalog_uden_advarsel_ved_lovlig_uge():
    from . import coach
    line = coach.build_bike_library_line(6, ["vo2_5x3", "z2_grundtur_80"])
    assert "ADVARSEL" not in line
