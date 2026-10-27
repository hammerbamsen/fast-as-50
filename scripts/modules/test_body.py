# -*- coding: utf-8 -*-
"""Tests for body.py — glidepath, korridor + 2-mandags-regel, fedt/FFM, cut-tjek, KPI'er."""
import json
import os
from datetime import date, timedelta

from modules import body

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

WP = {"startKg": 72.2, "targetKg": 68, "targetDate": "2027-01-31", "cutStartsFrom": "2026-09-21",
      "bodyFatPctStart": 21.8, "bodyFatPctTarget": 16, "holdFromMonth": "2027-02", "maxLossPerWeekKg": 0.25}


# Glidestien fra 11/9-2026 frosset (27/10-2026): logiktestene nedenfor bruger
# datoer i sep/okt 2026 og må ikke følge Kennets senere rekalibreringer af
# den rigtige plan.weightPlan (fx genstart efter virus: cut fra 2/11).
LEGACY_TDS_WEIGHT_PLAN = {
    "startKg": 72.2, "targetKg": 68, "targetDate": "2027-01-31", "bodyFatPctTarget": 16,
    "bodyFatPctStart": 21.8, "cutStartsFrom": "2026-09-21", "holdFromMonth": "2027-02",
    "maxLossPerWeekKg": 0.25,
    "note": "72,2 -> 68 kg over 19 uger fra 21/9 = 0,21 kg/uge (frosset testkopi).",
}


def _plan():
    with open(os.path.join(_ROOT, "data", "plan.json"), encoding="utf-8") as fh:
        plan = json.load(fh)
    plan["programs"]["tds-2027"]["weightPlan"] = dict(LEGACY_TDS_WEIGHT_PLAN)
    return plan


def series(end, days, fn, skip=()):
    """[{date, v, real}] for `days` dage t.o.m. end; fn(i) hvor i=0 er ældst."""
    end = date.fromisoformat(end) if isinstance(end, str) else end
    out = []
    for i in range(days):
        d = end - timedelta(days=days - 1 - i)
        if d.isoformat() in skip:
            out.append(None)
        else:
            out.append({"date": d.isoformat(), "v": round(fn(i), 2), "real": True})
    return out


def flat(end, days, v):
    return series(end, days, lambda i: v)


def on_glidepath(end, days, offset=0.0):
    """Serie der ligger præcis på glidepath + offset (før cut: startKg + offset)."""
    end = date.fromisoformat(end) if isinstance(end, str) else end

    def fn(i):
        d = end - timedelta(days=days - 1 - i)
        e = body.expected_kg(WP, d)
        return (e if e is not None else WP["startKg"]) + offset
    return series(end, days, fn)


# ── Faser og datoer ─────────────────────────────────────────────────────────

def test_phase_pre_cut_hold():
    assert body.phase_for(WP, date(2026, 9, 6)) == "pre"
    assert body.phase_for(WP, date(2026, 9, 21)) == "cut"
    assert body.phase_for(WP, date(2027, 1, 31)) == "cut"
    assert body.phase_for(WP, date(2027, 2, 1)) == "hold"
    assert body.phase_for({}, date(2026, 9, 6)) is None


def test_glidepath_dates_and_rate():
    g = body.glidepath(WP, date(2026, 9, 6), [])
    assert g["phase"] == "pre"
    assert g["cutWeeks"] == 19
    assert g["ratePerWeek"] == -0.22            # 4,2 kg / 18,86 uger
    assert g["cutStartIsoWeek"] == 39 and g["isoWeek"] == 36
    assert g["note"] == "cut starter uge 39 (21/9)"
    assert g["expectedKg"] is None and g["status"] is None
    assert g["series"][0] == {"date": "2026-09-21", "expected": 72.2}
    assert g["series"][-1] == {"date": "2027-01-31", "expected": 68.0}
    assert all(g["series"][i]["expected"] > g["series"][i + 1]["expected"] for i in range(len(g["series"]) - 1))


def test_expected_kg_linear():
    assert body.expected_kg(WP, "2026-09-21") == 72.2
    assert body.expected_kg(WP, "2027-01-31") == 68.0
    mid = date(2026, 9, 21) + timedelta(days=66)
    assert abs(body.expected_kg(WP, mid) - 70.1) < 0.05
    assert body.expected_kg(WP, "2026-09-20") is None
    assert body.expected_kg(WP, "2027-03-01") == 68.0


def test_cut_week_and_iso_week():
    g = body.glidepath(WP, date(2026, 10, 12), on_glidepath("2026-10-12", 60))
    assert g["phase"] == "cut" and g["cutWeek"] == 4 and g["cutWeeks"] == 19
    assert g["isoWeek"] == 42
    assert g["avg7"] is not None and g["status"] == "plan" and abs(g["delta"]) <= 0.05


# ── Korridor + 2-mandags-regel ──────────────────────────────────────────────

def test_status_inside_corridor_is_plan():
    g = body.glidepath(WP, date(2026, 10, 12), on_glidepath("2026-10-12", 60, offset=0.3))
    assert g["status"] == "plan" and g["note"] is None


def test_status_foran_requires_two_mondays():
    # 0,8 kg under hele vejen -> begge mandage under -> foran
    g = body.glidepath(WP, date(2026, 10, 14), on_glidepath("2026-10-14", 60, offset=-0.8))
    assert g["status"] == "foran"
    assert [m["status"] for m in g["mondays"]] == ["foran", "foran"]
    # kun de sidste 4 dage under -> forrige mandag var på plan -> 'plan' med note
    end = date(2026, 10, 14)
    s = series(end, 60, lambda i: (body.expected_kg(WP, end - timedelta(days=59 - i)) or 72.2)
               + (-1.5 if i >= 56 else 0.0))
    g2 = body.glidepath(WP, end, s)
    assert g2["delta"] < -0.5
    assert g2["status"] == "plan"
    assert "efter to mandage" in g2["note"]


def test_status_bagud_two_mondays():
    g = body.glidepath(WP, date(2026, 10, 12), on_glidepath("2026-10-12", 60, offset=0.9))
    assert g["status"] == "bagud" and g["delta"] == 0.9


def test_hold_phase_corridor():
    g = body.glidepath(WP, date(2027, 2, 15), flat("2027-02-15", 60, 68.7))
    assert g["phase"] == "hold" and g["expectedKg"] == 68.0 and g["corridorKg"] == 1.0
    assert g["status"] == "plan"
    g2 = body.glidepath(WP, date(2027, 2, 15), flat("2027-02-15", 60, 69.4))
    assert g2["status"] == "bagud"


def test_no_recent_weighins():
    g = body.glidepath(WP, date(2026, 10, 12), flat("2026-09-20", 30, 72.0))
    assert g["phase"] == "cut" and g["avg7"] is None and g["status"] is None
    assert "ingen vejninger" in g["note"]


def test_actual_rate_4w():
    s = series("2026-10-12", 60, lambda i: 74.0 - 0.05 * i)   # −0,35 kg/uge
    g = body.glidepath(WP, date(2026, 10, 12), s)
    assert abs(g["actualRate4w"] - (-0.35)) < 0.02


# ── Fedt / FFM ──────────────────────────────────────────────────────────────

def test_fat_status_and_expected():
    f = body.fat_status(WP, date(2026, 9, 6), flat("2026-09-06", 30, 21.9))
    assert f["avg14"] == 21.9 and f["expected"] is None and f["status"] is None
    f2 = body.fat_status(WP, date(2026, 10, 12), flat("2026-10-12", 30, 21.0))
    assert abs(f2["expected"] - 21.1) < 0.1 and f2["status"] == "plan"
    f3 = body.fat_status(WP, date(2026, 10, 12), flat("2026-10-12", 30, 22.0))
    assert f3["status"] == "bagud"


def test_ffm_and_status():
    m = body.ffm_status(WP, date(2026, 10, 12), flat("2026-10-12", 60, 72.0), flat("2026-10-12", 60, 21.0))
    assert m["now"] == 56.9 and m["change28d"] == 0.0 and m["status"] == "ok"
    assert m["target"] == 57.1
    # 1 kg FFM tabt på 4 uger (vægt ned, fedt uændret) -> warn
    w = series("2026-10-12", 60, lambda i: 73.0 - (1.3 if i >= 46 else 0.0))
    m2 = body.ffm_status(WP, date(2026, 10, 12), w, flat("2026-10-12", 60, 21.0))
    assert m2["change28d"] is not None and m2["change28d"] < -0.5 and m2["status"] == "warn"
    m3 = body.ffm_status(WP, date(2026, 10, 12), [], [])
    assert m3["now"] is None and m3["status"] is None


# ── Styrke ──────────────────────────────────────────────────────────────────

def test_strength_week_counts_done_only():
    ws = [{"day": "Man", "disc": "strength", "done": True}, {"day": "Tor", "disc": "strength", "done": False},
          {"day": "Tir", "disc": "bike", "done": True}]
    assert body.strength_week(ws, {"strengthPerWeek": 2}) == {"done": 1, "target": 2}
    assert body.strength_week(None, {}) == {"done": 0, "target": 2}
    assert body.next_strength_day(ws, date(2026, 10, 13)) == "torsdag"   # tirsdag
    assert body.next_strength_day(ws, date(2026, 10, 16)) is None         # fredag: ingen tilbage


def test_strength_log_and_by_week():
    acts = [{"type": "WeightTraining", "start_date_local": "2026-09-29T07:00:00", "name": "Styrke"},
            {"type": "WeightTraining", "start_date_local": "2026-09-29T18:00:00", "name": "Styrke 2"},  # samme dag
            {"type": "Ride", "start_date_local": "2026-09-30T07:00:00"},
            {"type": "Workout", "start_date_local": "2026-10-02T07:00:00"},
            {"type": "Strength", "start_date_local": "2026-10-06T07:00:00"}]
    log = body.strength_log_from_activities(acts, date(2026, 9, 14), date(2026, 10, 12))
    assert [e["date"] for e in log["sessions"]] == ["2026-09-29", "2026-10-02", "2026-10-06"]
    weeks = body.strength_by_week(log, date(2026, 10, 12))
    assert weeks == {"2026-09-14": 0, "2026-09-21": 0, "2026-09-28": 2, "2026-10-05": 1}
    assert body.strength_by_week(None, date(2026, 10, 12)) == {}
    # loggen dækker kun 10 dage -> kun uger helt inden for vinduet
    short = body.strength_log_from_activities(acts, date(2026, 10, 3), date(2026, 10, 12))
    assert list(body.strength_by_week(short, date(2026, 10, 12))) == ["2026-10-05"]


# ── Cut-tjek ────────────────────────────────────────────────────────────────

def _glide(today="2026-10-12", offset=0.0, weight=None):
    w = weight if weight is not None else on_glidepath(today, 60, offset)
    return body.glidepath(WP, date.fromisoformat(today), w), w


def _check(today="2026-10-12", weight=None, ffm=None, weeks=None, rhr=None, hrv=None, next_strength=None, af_log=None):
    g, w = _glide(today, weight=weight)
    return body.cut_check(g, ffm or {"change28d": 0.0}, weeks if weeks is not None else {"a": 2, "b": 2}, 2,
                          rhr, hrv, w, date.fromisoformat(today), next_strength=next_strength, af_log=af_log)


def test_cutcheck_inactive_in_pre_and_hold():
    g = body.glidepath(WP, date(2026, 9, 6), [])
    c = body.cut_check(g, {}, {}, 2, None, None, [], date(2026, 9, 6))
    assert c["active"] is False and c["level"] is None and c["text"] == "Aktiveres uge 39 (21/9)"
    g2 = body.glidepath(WP, date(2027, 3, 1), flat("2027-03-01", 30, 68.0))
    c2 = body.cut_check(g2, {}, {}, 2, None, None, [], date(2027, 3, 1))
    assert c2["active"] is False and "vedligehold" in c2["text"]


def test_cutcheck_on_plan():
    c = _check(rhr=flat("2026-10-12", 30, 44), hrv=flat("2026-10-12", 30, 60))
    assert c["active"] and c["level"] is None and c["text"] == "På plan — fortsæt"
    assert set(c["signals"]) == {"rate", "ffm", "strength", "recovery", "plateau", "alcohol"}
    assert all(s["level"] is None for s in c["signals"].values())


def test_cutcheck_missing_series_show_no_data():
    c = _check(weeks={}, ffm={"change28d": None})
    assert c["signals"]["recovery"]["text"] == "ingen data"
    assert c["signals"]["ffm"]["text"] == "ingen data"
    assert "ingen data" in c["signals"]["strength"]["text"]
    assert c["level"] is None and c["text"] == "På plan — fortsæt"


def test_cutcheck_rate_warn_and_act():
    w = series("2026-10-12", 60, lambda i: 73.0 - 0.07 * i)     # −0,49 kg/uge
    c = _check(weight=w)
    assert c["signals"]["rate"]["level"] == "warn" and c["level"] == "warn"
    assert "over 0,4 kg/uge" in c["text"]
    w2 = series("2026-10-12", 60, lambda i: 74.0 - 0.1 * i)     # −0,7 kg/uge
    c2 = _check(weight=w2, next_strength="torsdag")
    assert c2["signals"]["rate"]["level"] == "act" and c2["level"] == "act"
    assert "vedligehold i 3-4 dage" in c2["text"] and "styrke torsdag" in c2["text"]


def test_cutcheck_ffm_act_wins():
    w = series("2026-10-12", 60, lambda i: 74.0 - 0.1 * i)
    c = _check(weight=w, ffm={"change28d": -0.8})
    assert c["signals"]["ffm"]["level"] == "act" and c["level"] == "act"
    assert c["text"].startswith("Fedtfri masse −0,8 kg")


def test_cutcheck_strength_warn():
    c = _check(weeks={"2026-09-28": 1, "2026-10-05": 0})
    assert c["signals"]["strength"]["level"] == "warn" and c["level"] == "warn"
    assert "styrkepas to uger i træk" in c["text"]
    c2 = _check(weeks={"2026-09-28": 1, "2026-10-05": 2})
    assert c2["signals"]["strength"]["level"] is None


def test_cutcheck_recovery_warn():
    w = series("2026-10-12", 60, lambda i: 73.0 - 0.03 * i)     # falder
    rhr = series("2026-10-12", 30, lambda i: 42 if i < 16 else 45)
    hrv = series("2026-10-12", 30, lambda i: 60 if i < 16 else 54)
    c = _check(weight=w, rhr=rhr, hrv=hrv)
    assert c["signals"]["recovery"]["level"] == "warn"
    assert c["signals"]["recovery"]["value"]["rhr"] == 3.0
    assert "Hvilepuls op og HRV ned" in c["text"]
    # samme signaler men vægt stabil -> ingen advarsel
    c2 = _check(weight=flat("2026-10-12", 60, 72.0), rhr=rhr, hrv=hrv)
    assert c2["signals"]["recovery"]["level"] is None


def test_cutcheck_plateau_info():
    c = _check(weight=flat("2026-10-19", 60, 71.5), today="2026-10-19")
    assert c["signals"]["plateau"]["level"] == "info" and c["level"] == "info"
    assert c["text"].startswith("Plateau")


# ── KPI'er + advarsel ───────────────────────────────────────────────────────

def test_weight_fat_kpi_pre():
    b = {"glidepath": body.glidepath(WP, date(2026, 9, 6), flat("2026-09-06", 20, 72.5)),
         "fat": body.fat_status(WP, date(2026, 9, 6), flat("2026-09-06", 20, 21.9))}
    k = body.weight_kpi(b)
    assert k == {"value": "72,5", "unit": "kg", "sub": "cut starter uge 39", "color": body.COLOR_NEUTRAL}
    f = body.fat_kpi(b)
    assert f["value"] == "21,9" and f["sub"] == "14d-snit · cut starter uge 39" and f["color"] == body.COLOR_NEUTRAL


def test_weight_kpi_cut_colors():
    g_ahead = body.glidepath(WP, date(2026, 10, 12), on_glidepath("2026-10-12", 60, -0.8))
    k = body.weight_kpi({"glidepath": g_ahead})
    assert k["color"] == body.COLOR_OK and k["sub"].startswith("forventet 71,6 · foran 0,8")
    g_behind = body.glidepath(WP, date(2026, 10, 12), on_glidepath("2026-10-12", 60, 0.9))
    assert body.weight_kpi({"glidepath": g_behind})["color"] == body.COLOR_WARN
    g_plan = body.glidepath(WP, date(2026, 10, 12), on_glidepath("2026-10-12", 60, 0.2))
    k3 = body.weight_kpi({"glidepath": g_plan})
    assert k3["color"] == body.COLOR_OK and k3["sub"] == "forventet 71,6 · på plan"


def test_cut_warning_levels():
    assert body.cut_warning({"cutCheck": {"active": False, "level": None}}) is None
    assert body.cut_warning({"cutCheck": {"active": True, "level": "info", "text": "x"}}) is None
    w = body.cut_warning({"cutCheck": {"active": True, "level": "warn", "text": "Tabet er stort"}})
    assert w == {"type": "cut", "level": "warn", "message": "Cut-tjek: Tabet er stort"}
    assert body.cut_warning({"cutCheck": {"active": True, "level": "act", "text": "x"}})["level"] == "critical"


# ── Hele build_body mod rigtig plan.json ────────────────────────────────────

def test_build_body_real_plan_pre_and_cut():
    plan = _plan()
    wp, goals, prog = body.find_weight_plan(plan, "kennet", date(2026, 9, 6))
    assert prog["id"] == "tds-2027" and wp["cutStartsFrom"] == "2026-09-21" and goals["strengthPerWeek"] == 2
    data = {"weightHistory": flat("2026-09-06", 30, 72.5), "fatHistory": flat("2026-09-06", 30, 21.8),
            "week_sessions": [{"day": "Man", "disc": "strength", "done": True}]}
    b = body.build_body(plan, data, date(2026, 9, 6))
    assert b["glidepath"]["phase"] == "pre" and b["cutCheck"]["active"] is False
    assert b["strengthWeek"] == {"done": 1, "target": 2}
    json.dumps(b)   # serialiserbar
    data2 = {"weightHistory": on_glidepath("2026-10-12", 60, -0.4), "fatHistory": flat("2026-10-12", 60, 21.0),
             "rhrHistory": flat("2026-10-12", 30, 44), "hrvHistory": flat("2026-10-12", 30, 60), "week_sessions": []}
    b2 = body.build_body(plan, data2, date(2026, 10, 12))
    assert b2["glidepath"]["phase"] == "cut" and b2["glidepath"]["status"] == "plan"   # −0,4 inden for ±0,5
    assert b2["cutCheck"]["active"] and b2["cutCheck"]["signals"]["strength"]["text"].startswith("ingen data")
    json.dumps(b2)


def test_coach_context_picks_up_body():
    from modules import coach_context as cc
    plan = _plan()
    data = {"weightHistory": on_glidepath("2026-10-12", 60, -0.8), "fatHistory": flat("2026-10-12", 60, 21.0),
            "week_sessions": []}
    data["body"] = body.build_body(plan, data, date(2026, 10, 12))
    ctx = cc.build_context(plan, data, date(2026, 10, 12))
    cut = ctx["body"]["cut"]
    assert cut["active"] is True and cut["status"] == "foran" and cut["phase"] == "cut"
    assert cut["ffmKg"] == data["body"]["ffm"]["now"] and cut["checkText"]
    json.dumps(ctx)
    # uden data.body: uændret adfærd
    ctx2 = cc.build_context(plan, {"weightHistory": data["weightHistory"]}, date(2026, 10, 12))
    assert "status" not in ctx2["body"]["cut"]


# ── Alkohol-signal (blok 7) ────────────────────────────────────────────────

def _aflog(today, pattern):
    """pattern: str af 7 tegn ældst->i dag, '0' AF, '1' drik, '-' uregistreret."""
    t = date.fromisoformat(today)
    out = {}
    for i, ch in enumerate(pattern):
        if ch != '-':
            out[(t - timedelta(days=6 - i)).isoformat()] = int(ch)
    return out


def test_alcohol_signal_none_and_no_data():
    assert body.alcohol_signal(None, "2026-10-12")["level"] is None
    assert body.alcohol_signal({}, "2026-10-12")["text"] == "ingen registrering"
    s = body.alcohol_signal({"2026-09-01": 1}, "2026-10-12")
    assert s["level"] is None and "ingen registrering" in s["text"]


def test_alcohol_signal_ok_and_warn():
    ok = body.alcohol_signal(_aflog("2026-10-12", "0001000"), "2026-10-12")
    assert ok["level"] is None and ok["value"] == {"days7": 1, "run": 1} and ok["text"] == "1 drikkedag på 7 dage"
    spread = body.alcohol_signal(_aflog("2026-10-12", "1010100"), "2026-10-12")
    assert spread["level"] == "warn" and spread["value"]["days7"] == 3
    cluster = body.alcohol_signal(_aflog("2026-10-12", "0001100"), "2026-10-12")
    assert cluster["level"] == "warn" and cluster["value"] == {"days7": 2, "run": 2}
    assert cluster["text"] == "2 drikkedage på 7 dage · 2 i træk"
    # uregistreret dag bryder rækken
    broken = body.alcohol_signal(_aflog("2026-10-12", "0001-10"), "2026-10-12")
    assert broken["level"] is None and broken["value"] == {"days7": 2, "run": 1}


def test_cutcheck_alcohol_warn_text_and_priority():
    log = _aflog("2026-10-12", "0011100")
    c = _check(af_log=log)
    assert c["signals"]["alcohol"]["level"] == "warn" and c["level"] == "warn"
    assert c["text"] == "3 drikkedage på 7 dage · 3 i træk under cuttet — AF resten af ugen før du skærer mere"
    # restitution vinder over alkohol
    w = series("2026-10-12", 60, lambda i: 73.0 - 0.03 * i)
    rhr = series("2026-10-12", 30, lambda i: 42 if i < 16 else 45)
    hrv = series("2026-10-12", 30, lambda i: 60 if i < 16 else 54)
    c2 = _check(weight=w, rhr=rhr, hrv=hrv, af_log=log)
    assert c2["text"].startswith("Hvilepuls op og HRV ned")
    # uden log: signalet findes stadig, uden data
    c3 = _check()
    assert c3["signals"]["alcohol"]["level"] is None and "ingen registrering" in c3["signals"]["alcohol"]["text"]


def test_build_body_passes_af_log():
    from datetime import date as _d
    d = {"weightHistory": flat("2026-10-12", 60, 71.5), "fatHistory": flat("2026-10-12", 60, 21.0),
         "rhrHistory": flat("2026-10-12", 30, 42), "hrvHistory": flat("2026-10-12", 30, 60),
         "week_sessions": [], "af_log": _aflog("2026-10-12", "1110000")}
    b = body.build_body(_plan(), d, _d(2026, 10, 12))
    assert b["cutCheck"]["signals"]["alcohol"]["value"] == {"days7": 3, "run": 3}


# ── Fedtfri masse: hold-mål (blok 8) ───────────────────────────────────────

def test_ffm_baseline_floor_pre_is_now_and_ok():
    m = body.ffm_status(WP, date(2026, 9, 6), flat("2026-09-06", 30, 72.5), flat("2026-09-06", 30, 21.8))
    assert m["baseline"] == m["now"] and m["baselineDate"] == "2026-09-06"
    assert abs(m["floor"] - (m["now"] - 0.5)) < 0.06 and m["status"] == "ok" and m["holdKg"] == -0.5
    assert m["target"] == 57.1                                         # beholdes
    empty = body.ffm_status(WP, date(2026, 9, 6), [], [])
    assert empty["baseline"] is None and empty["floor"] is None and empty["status"] is None


def test_ffm_baseline_at_cut_start_and_floor_status():
    # 73,0 kg / 21 % frem til 29/9, derefter −1,3 kg: baseline måles 21/9 (cut-start)
    w = series("2026-10-12", 60, lambda i: 73.0 - (1.3 if i >= 46 else 0.0))
    m = body.ffm_status(WP, date(2026, 10, 12), w, flat("2026-10-12", 60, 21.0))
    assert m["baselineDate"] == "2026-09-21" and m["baseline"] == 57.7 and m["floor"] == 57.2
    assert m["now"] < m["floor"] and m["status"] == "warn"
    # samme baseline, vægt kun −0,3 kg -> over floor -> ok (selv om change28d er negativ)
    w2 = series("2026-10-12", 60, lambda i: 73.0 - (0.3 if i >= 46 else 0.0))
    m2 = body.ffm_status(WP, date(2026, 10, 12), w2, flat("2026-10-12", 60, 21.0))
    assert m2["baseline"] == 57.7 and m2["now"] >= m2["floor"] and m2["status"] == "ok"
    assert m2["change28d"] is not None and m2["change28d"] < 0


# ── Styrke-log + templates (blok 8) ────────────────────────────────────────

def _lib():
    return body.load_workout_library(os.path.join(_ROOT, "data", "workout_library.json"))


def test_workout_library_has_four_fs4_templates():
    tp = body.strength_templates(_lib())
    ids = [t["id"] for t in tp]
    assert ids == ["styrke-fs4-a-2r", "styrke-fs4-b-2r", "styrke-fs4-a-3r", "styrke-fs4-b-3r"]
    a2 = next(t for t in tp if t["id"] == "styrke-fs4-a-2r")
    assert a2["rounds"] == 2 and len(a2["exercises"]) == 5 and "Ben først" in a2["progression"]
    assert {e["group"] for e in a2["exercises"]} <= {"ben", "overkrop", "core"}
    assert all(set(e) == {"name", "load", "reps", "unit", "group"} for e in a2["exercises"])
    assert body.ab_of("Styrke A · Functional 4 · 2 runder") == "a"
    assert body.ab_of(None, "styrke-fs4-b-3r") == "b" and body.ab_of("Styrke Unilateral A 3 sæt") is None
    assert body.ab_of("Styrke B 2 sæt") == "b" and body.ab_of("Styrketræning") is None


def test_merge_strength_log_enriches_and_adds_logged_days():
    log = {"from": "2026-09-01", "to": "2026-09-28",
           "sessions": [{"date": "2026-09-12", "name": "Styrketræning"}, {"date": "2026-09-14", "name": "Styrketræning"}]}
    plog = {"2026-09-12": {"rpe": 7, "complete": 1, "note": "swing 16 næste gang", "template": "styrke-fs4-a-2r", "at": "x"},
            "2026-09-16": {"rpe": 8, "complete": 0, "note": "", "template": None, "at": "y"},
            "2026-08-01": {"rpe": 5, "complete": 1, "note": "", "template": None, "at": "z"}}   # uden for vinduet
    m = body.merge_strength_log(log, plog)
    assert [s["date"] for s in m["sessions"]] == ["2026-09-12", "2026-09-14", "2026-09-16"]
    s12, s14, s16 = m["sessions"]
    assert s12["rpe"] == 7 and s12["complete"] == 1 and s12["template"] == "styrke-fs4-a-2r" and s12["source"] == "activity"
    assert s14["rpe"] is None and s14["complete"] is None and s14["note"] == "" and s14["source"] == "activity"
    assert s16["source"] == "log" and s16["rpe"] == 8 and s16["name"] == "Styrke (logget)"
    assert body.merge_strength_log(log, None)["sessions"][0]["rpe"] is None
    assert body.merge_strength_log(None, plog)["sessions"] and "from" not in body.merge_strength_log(None, plog)


def test_next_strength_from_plan_then_alternating():
    tp = _lib()
    plan = {"athletes": {"kennet": {"days": [
        {"date": "2026-09-14", "entries": [{"id": "x1", "workout": {"type": "WeightTraining", "name": "Styrke A · Functional 4 · 2 runder"},
                                            "libraryId": "styrke-fs4-a-2r", "done": True}]},
        {"date": "2026-09-16", "entries": [{"id": "x2", "workout": {"type": "WeightTraining", "name": "Styrke B · Functional 4 · 2 runder"},
                                            "templateId": "styrke-fs4-b-2r"}]},
    ]}}}
    log = {"from": "2026-08-20", "to": "2026-09-15", "sessions": [
        {"date": "2026-09-14", "name": "Styrketræning", "template": "styrke-fs4-a-2r", "rpe": 7, "complete": 1, "note": ""}]}
    n = body.next_strength(plan, log, date(2026, 9, 15), tp)
    assert n["ab"] == "b" and n["templateId"] == "styrke-fs4-b-2r" and n["date"] == "2026-09-16"
    assert n["reasoning"] == "Planlagt 16/9: Styrke B · Functional 4 · 2 runder" and n["name"].startswith("Styrke B")
    # gennemført pas springes over; ingen fremtidige -> skiftevis ud fra loggen
    plan["athletes"]["kennet"]["days"][1]["entries"][0]["done"] = True
    n2 = body.next_strength(plan, log, date(2026, 9, 17), tp)
    assert n2["ab"] == "b" and n2["templateId"] == "styrke-fs4-b-2r" and n2["date"] is None
    assert n2["reasoning"] == "Skiftevis A/B: seneste var A (14/9)"
    # ingen A/B nogen steder -> A
    n3 = body.next_strength({"athletes": {"kennet": {"days": []}}}, {"sessions": [{"date": "2026-09-01", "name": "Styrketræning"}]},
                            date(2026, 9, 17), tp)
    assert n3["ab"] == "a" and n3["templateId"] == "styrke-fs4-a-2r" and "start med A" in n3["reasoning"]
    # 3 runder fra uge 41 når de to seneste afsluttede uger har ≥ 2 pas
    log3 = {"from": "2026-09-14", "to": "2026-10-11", "sessions": [
        {"date": d, "name": "Styrketræning", "template": "styrke-fs4-b-2r"} for d in
        ("2026-09-28", "2026-10-01", "2026-10-05", "2026-10-08")]}
    n4 = body.next_strength({"athletes": {"kennet": {"days": []}}}, log3, date(2026, 10, 12), tp)   # uge 42
    assert n4["ab"] == "a" and n4["templateId"] == "styrke-fs4-a-3r" and n4["rounds"] == 3
    log2 = dict(log3, sessions=log3["sessions"][:3])   # kun 1 pas i seneste uge -> 2 runder
    n5 = body.next_strength({"athletes": {"kennet": {"days": []}}}, log2, date(2026, 10, 12), tp)
    assert n5["rounds"] == 2


def test_build_strength_last4_newest_first():
    log = {"from": "2026-08-20", "to": "2026-09-15", "sessions": [
        {"date": f"2026-09-{d:02d}", "name": "Styrketræning", "template": t, "rpe": r, "complete": c, "note": n}
        for d, t, r, c, n in ((1, None, None, None, None), (3, "styrke-fs4-a-2r", 7, 1, "ok"),
                              (5, "styrke-fs4-b-2r", 8, 0, "tung"), (8, "styrke-fs4-a-2r", 6, 1, ""),
                              (10, "styrke-fs4-b-2r", 7, 1, "swing 16 næste gang"))]}
    s = body.build_strength({"athletes": {"kennet": {"days": []}}}, log, date(2026, 9, 12), templates=_lib())
    assert [x["date"] for x in s["last4"]] == ["2026-09-10", "2026-09-08", "2026-09-05", "2026-09-03"]
    assert s["last4"][0] == {"date": "2026-09-10", "name": "Styrketræning", "ab": "b", "rpe": 7, "complete": 1, "note": "swing 16 næste gang"}
    assert s["next"]["ab"] == "a" and len(s["templates"]) == 4
    json.dumps(s)
