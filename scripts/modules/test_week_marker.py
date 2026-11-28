# -*- coding: utf-8 -*-
"""Tests for week_marker — heldags-ugemarkering i Outlook (27/11-2026)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import week_marker as wm

LEJR = {"week": 28, "start": "2027-03-15", "end": "2027-03-21", "phase": "BUILD",
        "blockType": "CAMP", "location": "Mallorca", "ctlTarget": 66, "tssTarget": 680,
        "purpose": "Lejr #1: volumen og aerob base. 18-22 t, ét hårdt pas.",
        "note": "LEJR #1 Mallorca 14-21/3.", "keySession": "Sa Calobra tir 16/3",
        "quota": {"haard": 1, "moderat": 2},
        "travel": [{"label": "Mallorca lejr #1"}]}
HJEM = {"week": 30, "start": "2027-03-29", "phase": "BUILD", "blockType": "BUILD",
        "location": "Gentofte", "ctlTarget": 65, "tssTarget": 520,
        "purpose": "Build hjemme. Søndag 4,5-5 t."}


def test_emnet_kan_laeses_i_en_kalender():
    assert wm.subject(LEJR) == "KU11 · CAMP · Mallorca — Lejr #1: volumen og aerob base"
    # Gentofte er standard og fylder bare — det staar ikke i emnet
    assert wm.subject(HJEM) == "KU13 · BUILD — Build hjemme"
    # emnet afkortes, saa kalenderen ikke faar en roman
    lang = dict(HJEM, purpose="x" * 400)
    assert len(wm.subject(lang)) <= wm.EMNE_MAX


def test_body_har_noegletal_formaal_og_fingeraftryk():
    b = wm.body(LEJR)
    for forventet in ("Fase: BUILD", "Blok: CAMP", "Sted: Mallorca", "CTL-mål: 66",
                      "TSS-mål: 680", "Kvote: haard 1, moderat 2", "Formål:",
                      "Nøglepas: Sa Calobra tir 16/3", "Note:", "Rejse: Mallorca lejr #1"):
        assert forventet in b, forventet
    assert f"sync:{wm.fingerprint(LEJR)}" in b
    assert wm.fingerprint_i_event({"body": {"content": b}}) == wm.fingerprint(LEJR)


def test_fingeraftryk_aendrer_sig_kun_naar_indholdet_gor():
    f0 = wm.fingerprint(LEJR)
    assert wm.fingerprint(dict(LEJR)) == f0                      # samme data
    assert wm.fingerprint(dict(LEJR, tssActual=999)) == f0       # felt der ikke vises
    assert wm.fingerprint(dict(LEJR, blockType="BUILD")) != f0
    assert wm.fingerprint(dict(LEJR, purpose="noget andet")) != f0
    assert wm.fingerprint(dict(LEJR, quota={"haard": 2, "moderat": 2})) != f0
    assert wm.fingerprint(dict(LEJR, travel=[])) != f0


def test_eventet_er_heldags_og_blokerer_ikke_tid():
    e = wm.event(LEJR)
    assert e["isAllDay"] is True and e["showAs"] == "free"
    assert e["start"]["dateTime"].startswith("2027-03-15")
    assert e["end"]["dateTime"].startswith("2027-03-22")         # eksklusiv slut
    assert e["categories"] == ["Ugeplan"]


def test_kategorien_maa_ikke_indeholde_ning():
    """build_workouts.outlook_delete_by_date sletter alt med 'ning' i kategori
    eller emne. Hed kategorien 'Traeningsuge', ville traeningssynken rydde
    markeringerne."""
    assert "ning" not in wm.KATEGORI.encode("ascii", "ignore").decode().lower()


def test_er_markering_skelner_fra_traeningspas():
    assert wm.er_markering({"categories": ["Ugeplan"]})
    assert wm.er_markering({"subject": "KU11 · CAMP · Mallorca", "isAllDay": True})
    assert not wm.er_markering({"subject": "Cykel Z2 2 t", "categories": ["Træning"]})
    assert not wm.er_markering({"subject": "KU11 noget", "isAllDay": False})
    assert not wm.er_markering({})
    assert not wm.er_markering(None)


def test_plan_weeks_vinduet():
    plan = {"programs": {"p": {"id": "p", "start": "2027-01-04", "weeks": [
        {"week": 1, "start": "2027-01-04"}, {"week": 2, "start": "2027-01-11"},
        {"week": 3, "start": "2027-01-18"}, {"week": 4}]}}}
    alle = wm.plan_weeks(plan, "p")
    assert [w["week"] for w in alle] == [1, 2, 3]           # uge uden start springes
    vindue = wm.plan_weeks(plan, "p", fra="2027-01-11", til="2027-01-11")
    assert [w["week"] for w in vindue] == [2]
    assert all(w["programId"] == "p" for w in alle)


def test_mod_den_rigtige_plan_uden_at_laase_indhold():
    import json
    plan = json.loads((Path(__file__).resolve().parent.parent.parent / "data" / "plan.json")
                      .read_text(encoding="utf-8"))
    uger = wm.plan_weeks(plan, "tds-2027")
    assert len(uger) > 40
    for w in uger:
        e = wm.event(w)
        assert e["subject"].startswith("KU") and len(e["subject"]) <= wm.EMNE_MAX
        assert e["isAllDay"] and e["categories"] == [wm.KATEGORI]
        assert wm.fingerprint_i_event({"body": e["body"]}) == wm.fingerprint(w)
