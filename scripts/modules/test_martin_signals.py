# -*- coding: utf-8 -*-
"""Tests for martin_signals.py — relevansfilter og md-format."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import martin_signals as ms


def mk(days):
    return {"program": {"start": "2026-06-01", "totalWeeks": 14},
            "athletes": {"kennet": {"days": days}}}


def d(d_iso, *wos):
    return {"date": d_iso, "entries": [{"workout": w} for w in wos]}


EASY30 = {"name": "Cykel Z2 let", "type": "Ride", "moving_time": 1800}
EASY45 = {"name": "Cykel Z2 let", "type": "Ride", "moving_time": 2700}
VO2 = {"name": "Løb VO2 5×3 Z4", "type": "Run", "moving_time": 2700}
LONG = {"name": "Cykel Z2 lang", "type": "Ride", "moving_time": 3 * 3600}


def test_small_easy_change_is_noise():
    old = mk([d("2026-06-04", EASY30)])
    new = mk([d("2026-06-05", EASY30), d("2026-06-04")])
    assert ms.build_signal(old, new, "move", ["2026-06-04", "2026-06-05"]) is None


def test_hard_session_added_signals():
    old = mk([d("2026-06-04")])
    new = mk([d("2026-06-04", VO2)])
    sig = ms.build_signal(old, new, "add", ["2026-06-04"])
    assert sig and "VO2" in sig and "[hårdt]" in sig and "hviledag" in sig


def test_long_session_moved_signals():
    old = mk([d("2026-06-04", LONG), d("2026-06-06")])
    new = mk([d("2026-06-04"), d("2026-06-06", LONG)])
    sig = ms.build_signal(old, new, "move", ["2026-06-04", "2026-06-06"])
    assert sig and sig.count("[langt]") >= 2 and "uge 1" in sig


def test_duration_delta_45min_signals():
    old = mk([d("2026-06-04", EASY30)])
    new = mk([d("2026-06-04", EASY30, EASY45)])
    sig = ms.build_signal(old, new, "add", ["2026-06-04"])
    assert sig is not None


def test_eva_edits_never_signal():
    old = mk([d("2026-06-04")])
    new = mk([d("2026-06-04", VO2)])
    assert ms.build_signal(old, new, "add", ["2026-06-04"], athlete="eva") is None


def test_append_creates_header_and_appends():
    sig = "\n### Planændring 07/07 15:00\n- test\n"
    md = ms.append_signal("", sig)
    assert md.startswith("# Signaler til Martin")
    md2 = ms.append_signal(md, sig)
    assert md2.count("### Planændring") == 2
    assert md2.count("# Signaler til Martin —") == 1


# ── Ugentlig Martin-mail (blok 8) ───────────────────────────────────────────

from datetime import date, timedelta


def _series(end, n, fn):
    end = date.fromisoformat(end)
    return [{"date": (end - timedelta(days=n - 1 - i)).isoformat(), "v": fn(i), "real": True} for i in range(n)]


def _plan_w(days=()):
    weeks = [{"week": w, "start": (date(2026, 9, 7) + timedelta(weeks=w - 1)).isoformat(),
              "blockType": bt, "ctlTarget": ct, "tssTarget": ts}
             for w, bt, ct, ts in ((1, "RECOVERY", 47, 150), (2, "RACE", 45, 250), (3, "BASE", 48, 380))]
    return {"programs": {"tds-2027": {"start": "2026-09-07", "end": "2027-08-29", "totalWeeks": 51,
                                      "athletes": ["kennet"], "weeks": weeks,
                                      "goals": {"strengthPerWeek": 2}}},
            "athletes": {"kennet": {"days": list(days)}}}


def _data_w():
    end = "2026-09-13"
    return {
        "weekTss": {"actual": 212, "planned": 255}, "ctlCurve": [48.1, 49.9], "tsb": -3.4,
        "body": {"glidepath": {"phase": "pre", "avg7": 72.3, "note": "cut starter uge 39 (21/9)"},
                 "fat": {"avg14": 21.6}, "strengthWeek": {"done": 1, "target": 2},
                 "cutCheck": {"active": False, "level": None, "text": "Aktiveres uge 39 (21/9)"}},
        "hrvHistory": _series(end, 28, lambda i: 60.0 if i < 21 else 54.0),
        "rhrHistory": _series(end, 28, lambda i: 44),
        "sleepHistory": _series(end, 28, lambda i: 7.3),
        "af_log": {(date(2026, 9, 13) - timedelta(days=i)).isoformat(): (1 if i in (1, 2) else 0) for i in range(7)},
        "checkinLog": [{"date": (date(2026, 9, 13) - timedelta(days=i)).isoformat(),
                        "protein": 2 if i < 4 else 1, "sult": 2 if i == 0 else 0} for i in range(6, -1, -1)],
        "strengthLog": {"from": "2026-08-17", "to": "2026-09-13", "sessions": [
            {"date": "2026-09-05", "name": "Styrketræning", "rpe": 8, "complete": 0, "note": "tung"},
            {"date": "2026-09-09", "name": "Styrketræning", "rpe": 7, "complete": 1, "note": ""},
            {"date": "2026-09-12", "name": "Styrketræning", "rpe": None, "complete": None, "note": ""}]},
    }


def _wo(name, typ, mins, **kw):
    return {"id": kw.pop("id", name[:6]), "workout": {"name": name, "type": typ, "moving_time": mins * 60}, **kw}


def test_build_weekly_eight_lines_from_data():
    days = [d("2026-09-15", {"name": "Løb VO2 5×3 min", "type": "Run", "moving_time": 2700}),
            {"date": "2026-09-19", "entries": [_wo("Cykel Z2 90 min", "Ride", 130, id="z2dep", libraryId="z2_depottur_2t")]},
            {"date": "2026-09-16", "entries": [_wo("Styrke A · 2 runder", "WeightTraining", 100)]},   # styrke tæller aldrig
            {"date": "2026-09-17", "entries": [_wo("Cykel Z2 60 min", "Ride", 60)]}]
    md = "# x\n\n### Planændring 01/09\n- a\n\n### Signaler uge 36\n- b\n\n### Planændring 10/09\n- c\n\n### Planændring 12/09\n- d\n"
    r = ms.build_weekly(_data_w(), _plan_w(days), date(2026, 9, 13), signals_md=md)
    assert r["week"] == 1 and r["isoWeek"] == 37 and len(r["lines"]) == 8 and r["generatedAt"].endswith("Z")
    L = r["lines"]
    assert L[0] == "Uge 37: TSS 212 af 255 (83 %) · CTL 49,9 (mål 47) · TSB −3,4"
    assert L[1] == "Vægt 7d 72,3 kg · fedt 14d 21,6 % · cut starter uge 39 (21/9)"
    assert L[2] == "HRV 7d 54 (28d 58) · hvilepuls 44 · søvn 7d 7,3 t"
    assert L[3] == "AF 5/7 · protein 3/3 4/7 · aftensult 1/7"
    assert L[4] == "Styrke 2/2 · check-in —"
    assert L[5] == "Cut-tjek: inaktivt — Aktiveres uge 39 (21/9)"
    assert L[6] == ("Næste uge (38, RACE): TSS-mål 250 · hårde/lange dage: "
                    "tir 15/9 Løb VO2 5×3 min 45 min, lør 19/9 Cykel Z2 90 min 130 min")
    assert L[7] == "Planændringer siden sidst: 2 — se martin_signals.md"


def test_build_weekly_missing_data_gives_dashes_never_guesses():
    r = ms.build_weekly({}, {}, date(2026, 9, 13))
    L = r["lines"]
    assert r["week"] is None and len(L) == 8
    assert L[0] == "Uge 37: TSS — af — (— %) · CTL — (mål —) · TSB —"
    assert L[1] == "Vægt 7d — kg · fedt 14d — % · intet cut i planen"
    assert L[2] == "HRV 7d — (28d —) · hvilepuls — · søvn 7d — t"
    assert L[3] == "AF —/7 · protein 3/3 —/7 · aftensult —/7"
    assert L[4] == "Styrke —/2 · check-in —"
    assert L[5] == "Cut-tjek: inaktivt — intet cut i planen"
    assert L[6] == "Næste uge (38, —): TSS-mål — · hårde/lange dage: ingen"
    assert L[7] == "Planændringer siden sidst: — — se martin_signals.md"


def test_build_weekly_cut_status_and_fallbacks():
    data = _data_w()
    data.pop("weekTss")
    data["week_sessions"] = [{"planned_tss": 100, "actual_tss": 80}, {"planned_tss": 50, "actual_tss": 0},
                             {"planned_tss": 0, "actual_tss": 30, "extra": True}]
    data["body"]["glidepath"] = {"phase": "cut", "status": "bagud", "delta": 0.7, "expectedKg": 71.4, "avg7": 72.1}
    data["body"]["cutCheck"] = {"active": True, "level": "warn", "text": "Tabet er over 0,4 kg/uge — læg 200-300 kcal på"}
    data["strengthLog"]["sessions"][1]["complete"] = 0
    r = ms.build_weekly(data, _plan_w(), date(2026, 9, 13))
    L = r["lines"]
    assert L[0].startswith("Uge 37: TSS 110 af 150 (73 %)")
    assert L[1].endswith("· bagud 0,7 kg mod glidepath (71,4)")
    assert L[4] == "Styrke 2/2 · check-in —"
    assert L[5] == "Cut-tjek: warn — Tabet er over 0,4 kg/uge — læg 200-300 kcal på"
    data["body"]["cutCheck"]["level"] = None
    assert ms.build_weekly(data, _plan_w(), date(2026, 9, 13))["lines"][5].startswith("Cut-tjek: ok —")


def test_weekly_md_helpers():
    md = "# x\n\n### Planændring 01/09\n- a\n"
    assert ms.count_plan_changes_since_last_weekly(md) == 1
    assert ms.count_plan_changes_since_last_weekly("") == 0
    assert not ms.has_weekly(md, 37)
    mail = {"isoWeek": 37, "lines": ["l1", "l2"]}
    out = ms.append_signal(md, ms.format_weekly(mail))
    assert out.endswith("\n### Signaler uge 37\n- l1\n- l2\n")
    assert ms.has_weekly(out, 37) and not ms.has_weekly(out, 3) and not ms.has_weekly(out, 370)
    assert ms.count_plan_changes_since_last_weekly(out) == 0


def test_strength_line_uses_checkin_when_present():
    data = dict(_data_w())
    data["strength"] = {"checkin": {"last": {"date": "2026-10-04", "legs": 1, "upper": 0}}}
    r = ms.build_weekly(data, _plan_w([]), date(2026, 10, 11))
    assert r["lines"][4].endswith("· check-in 4/10 ben ✓ overkrop ✗")
