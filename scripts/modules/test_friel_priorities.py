# -*- coding: utf-8 -*-
"""Tests for friel_priorities — Friels tabel 6.5 og 6.6 (28/11-2026)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import friel_priorities as fp

UGER = [  # en lille sæson: 2 Prep, 4 Early Base, 3 Build
    {"week": 1, "start": "2027-01-04", "phase": "Preparation"},
    {"week": 2, "start": "2027-01-11", "phase": "Preparation"},
    {"week": 3, "start": "2027-01-18", "phase": "Early Base"},
    {"week": 4, "start": "2027-01-25", "phase": "Early Base"},
    {"week": 5, "start": "2027-02-01", "phase": "Early Base"},
    {"week": 6, "start": "2027-02-08", "phase": "Early Base"},
    {"week": 7, "start": "2027-02-15", "phase": "Build 1"},
    {"week": 8, "start": "2027-02-22", "phase": "Build 1"},
    {"week": 9, "start": "2027-03-01", "phase": "Build 1"},
]


def test_kolonnen_bestemmes_af_loebets_varighed():
    assert fp.varighed_kolonne(9) == ">4t"      # TdS Ultrafondo
    assert fp.varighed_kolonne(5.5) == ">4t"    # Stelvio
    assert fp.varighed_kolonne(4) == "2-4t"     # 4 timer praecis er ikke OVER 4
    assert fp.varighed_kolonne(2) == "2-4t"
    assert fp.varighed_kolonne(1.5) == "<2t"
    assert fp.varighed_kolonne(None) == ">4t"   # default: Kennets maal


def test_tabel_66_over_fire_timer():
    """Raekkefoelgen er Friels egen og maa ikke drifte."""
    p = lambda f: fp.prioriteter(f, timer=9)
    assert p("Preparation") == ["Aerob tærskel", "Styrke", "Aerob kapacitet"]
    assert p("Early Base") == ["Styrke", "Aerob tærskel", "Aerob kapacitet"]
    assert p("Late Base") == ["Aerob kapacitet", "Aerob tærskel", "Laktattærskel", "Styrke"]
    assert p("Build") == ["Aerob tærskel", "Laktattærskel", "Aerob kapacitet", "Styrke"]
    assert p("Peak") == ["Laktattærskel", "Styrke"]
    assert p("Race") == ["Laktattærskel"]
    assert p("Transition") == ["Hvil"]


def test_kort_loeb_vender_prioriteten_i_build():
    """Under 2 timer er aerob kapacitet nummer et i Build — over 4 timer er den nummer tre.
    Det er hele pointen med at kolonnen findes."""
    lang = fp.prioriteter("Build", timer=9)
    kort_ = fp.prioriteter("Build", timer=1.5)
    assert lang[0] == "Aerob tærskel" and lang.index("Aerob kapacitet") == 2
    assert kort_[0] == "Aerob kapacitet"


def test_normaliser_haandterer_nummererede_faser():
    assert fp.normaliser("Build 1") == "Build"
    assert fp.normaliser("Build 2") == "Build"
    assert fp.normaliser("Peak 2") == "Peak"
    assert fp.normaliser("LATE BASE") == "Late Base"
    assert fp.normaliser("BASE+") == "Late Base"
    assert fp.normaliser("SPECIFIK") == "Build"
    assert fp.normaliser("TAPER") == "Peak"
    assert fp.normaliser(None) is None
    assert fp.normaliser("Fantasifase") is None
    assert fp.prioriteter("Fantasifase") == []


def test_varighed_mod_tabel_65():
    assert fp.varighed_ok("Build 1", 7) == (True, 6, 9)
    assert fp.varighed_ok("Build", 13) == (False, 6, 9)     # for lang
    assert fp.varighed_ok("Build", 4) == (False, 6, 9)      # for kort
    assert fp.varighed_ok("Peak", 2) == (True, 1, 2)
    assert fp.varighed_ok("Late Base", 6) == (True, 3, 6)
    assert fp.varighed_ok("Ukendt", 3) == (None, None, None)


def test_faser_i_plan_samler_sammenhaengende_afsnit():
    a = fp.faser_i_plan(UGER)
    assert [x["fase"] for x in a] == ["Preparation", "Early Base", "Build 1"]
    assert [x["uger"] for x in a] == [2, 4, 3]
    assert a[0]["fra"] == 1 and a[0]["til"] == 2
    assert a[2]["ok"] is False and a[2]["max"] == 9    # Build paa 3 uger er for kort
    assert a[1]["ok"] is True                          # Early Base paa 4 uger er fint
    assert fp.faser_i_plan([]) == []


def test_kort_viser_hvor_i_fasen_man_er():
    k = fp.kort(UGER, denne_uge=5, timer=9)
    assert k["navn"] == "Early Base" and k["fase"] == "Early Base"
    assert k["uge_i_fasen"] == 3 and k["uger_i_alt"] == 4 and k["tilbage"] == 1
    # 28/11-2026: testen laaste den gamle fejl fast — "slutter" var sidste uges
    # START (08/02). Fasen slutter soendag, altsaa 14/02, og naeste fase
    # begynder mandagen efter.
    assert k["slutter"] == "2027-02-14"
    assert k["naeste_start"] == "2027-02-15"
    assert k["naeste"] == "Build 1"
    assert k["prioriteter"][0] == "Styrke"
    assert "Maksimér styrke" in k["formaal"]
    assert k["kolonne"] == ">4t"


def test_kort_uden_for_faserne_og_paa_tom_plan():
    assert fp.kort([], denne_uge=1) is None
    k = fp.kort(UGER, denne_uge=99, timer=9)
    assert k["fase"] == "Preparation"       # falder tilbage paa foerste afsnit
    k2 = fp.kort(UGER, timer=9)             # ingen ugeangivelse
    assert k2["uge_i_fasen"] is None and k2["tilbage"] is None


def test_mod_den_rigtige_plan_uden_at_laase_faserne():
    """Kontrakten mod data.json — uden at laase hvilke faser planen har nu."""
    import json
    d = json.loads((Path(__file__).resolve().parent.parent.parent / "data.json")
                   .read_text(encoding="utf-8"))
    uger = (d.get("planTab") or {}).get("weeks") or []
    if not uger:
        return
    k = fp.kort(uger, denne_uge=(d.get("meta") or {}).get("week"), timer=9)
    assert k is not None and k["afsnit"]
    for a in k["afsnit"]:
        assert a["uger"] >= 1 and a["fra"] <= a["til"]


def _kort_plan():
    """Fixture: tre faser over seks uger, mandagsdatoer. Egne tal — ikke lånt
    fra plan.json, så et forslag ikke kan gøre testen rød."""
    return [
        {"week": 1, "start": "2027-01-04", "phase": "Early Base"},
        {"week": 2, "start": "2027-01-11", "phase": "Early Base"},
        {"week": 3, "start": "2027-01-18", "phase": "Early Base"},
        {"week": 4, "start": "2027-01-25", "phase": "Late Base"},
        {"week": 5, "start": "2027-02-01", "phase": "Late Base"},
        {"week": 6, "start": "2027-02-08", "phase": "Late Base"},
    ]


def test_kort_slutter_er_fasens_sidste_dag_ikke_sidste_uges_start():
    """28/11-2026: 'slutter' var sidste uges START, så kortet skrev at næste
    fase begyndte fem dage FØR i dag. Fasen slutter søndag."""
    k = fp.kort(_kort_plan(), 2)
    assert k["fase"] == "Early Base"
    # uge 3 starter mandag 18/1, så fasen slutter søndag 24/1
    assert k["slutter"] == "2027-01-24", k["slutter"]


def test_kort_naeste_start_er_naeste_fases_foerste_dag():
    k = fp.kort(_kort_plan(), 2)
    assert k["naeste"] == "Late Base"
    assert k["naeste_start"] == "2027-01-25", k["naeste_start"]
    # mandagen efter at fasen slutter — ingen huller, ingen overlap
    from datetime import date, timedelta
    assert (date.fromisoformat(k["naeste_start"])
            - date.fromisoformat(k["slutter"])) == timedelta(days=1)


def test_kort_sidste_fase_har_ingen_naeste():
    k = fp.kort(_kort_plan(), 6)
    assert k["fase"] == "Late Base"
    assert k["naeste"] is None and k["naeste_start"] is None
    assert k["slutter"] == "2027-02-14"
