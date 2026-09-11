# -*- coding: utf-8 -*-
"""
FTP-sporing (blok 13, 11/9-2026): aktuel FTP mod fasemålet i season2027,
W/kg på 7-dages vægt, næste FTP-test i planen og testhistorik.

Kilder i plan.json:
  athletes.kennet.zones.ftpW          — aktuel FTP (sandheden; skrives af set_zones)
  athletes.kennet.ftpHistory[]        — [{date, ftpW, source}] — fyldes af set_zones
                                        (edit_apply) når ftpW ændres, ellers i hånden
  season2027.phases[]                 — {name, weekFrom, weekTo, ftpTarget, wkgTarget}
  athletes.kennet.days[].entries[]    — libraryId 'test_ftp20' = næste test

Ren logik, ingen netværk. Farver som resten af KPI'erne:
  grøn  = FTP >= fasemål
  orange = inden for 3 % af fasemål
  rød   = mere end 3 % under fasemål
"""
from __future__ import annotations

from datetime import date

GREEN, ORANGE, RED, NEUTRAL = "#27AE60", "#E67E22", "#C0392B", "#7A6A58"
TEST_IDS = ("test_ftp20",)


def _to_date(d):
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def history(plan: dict, athlete: str = "kennet") -> list:
    ath = (plan.get("athletes") or {}).get(athlete) or {}
    rows = [dict(r) for r in (ath.get("ftpHistory") or []) if r.get("ftpW")]
    rows.sort(key=lambda r: str(r.get("date", "")))
    return rows


def record(plan: dict, ftp_w: int, when, source: str = "set_zones",
           athlete: str = "kennet") -> bool:
    """Tilføj en post til ftpHistory hvis FTP er ny. Muterer plan. True = tilføjet."""
    ath = plan["athletes"][athlete]
    rows = ath.setdefault("ftpHistory", [])
    if rows and int(rows[-1].get("ftpW", 0)) == int(ftp_w):
        return False
    rows.append({"date": _to_date(when).isoformat(), "ftpW": int(ftp_w), "source": source})
    return True


def phase_for(plan: dict, week_num) -> dict | None:
    phases = (plan.get("season2027") or {}).get("phases") or []
    if week_num is None:
        return None
    for p in phases:
        if p.get("weekFrom", 0) <= week_num <= p.get("weekTo", 0):
            return p
    return None


def next_test(plan: dict, today, athlete: str = "kennet") -> str | None:
    t = _to_date(today)
    for d in (plan["athletes"][athlete].get("days") or []):
        if _to_date(d["date"]) < t:
            continue
        for e in d.get("entries") or []:
            wo = e.get("workout") or {}
            if e.get("libraryId") in TEST_IDS or "FTP" in str(wo.get("name", "")).upper():
                return d["date"]
    return None


def build(plan: dict, today, weight_avg7=None, week_num=None,
          athlete: str = "kennet") -> dict:
    zones = plan["athletes"][athlete].get("zones") or {}
    ftp = zones.get("ftpW")
    ftp = int(ftp) if ftp else None
    phase = phase_for(plan, week_num) or {}
    target = phase.get("ftpTarget")
    season = plan.get("season2027") or {}
    wkg = round(ftp / float(weight_avg7), 2) if ftp and weight_avg7 else None
    if ftp is None or not target:
        status, color = "none", NEUTRAL
    elif ftp >= target:
        status, color = "ok", GREEN
    elif ftp >= target * 0.97:
        status, color = "warn", ORANGE
    else:
        status, color = "bagud", RED
    return {
        "ftpW": ftp,
        "wkg": wkg,
        "weightAvg7": round(float(weight_avg7), 1) if weight_avg7 else None,
        "phase": phase.get("name"),
        "phaseTarget": target,
        "phaseWkgTarget": phase.get("wkgTarget"),
        "seasonTarget": season.get("ftpTarget"),
        "seasonStart": season.get("ftpStart"),
        "status": status,
        "color": color,
        "nextTest": next_test(plan, today, athlete),
        "history": history(plan, athlete),
        "phases": [{"name": p.get("name"), "weekFrom": p.get("weekFrom"), "weekTo": p.get("weekTo"),
                    "ftpTarget": p.get("ftpTarget")} for p in (season.get("phases") or [])],
    }


def _dk(iso: str | None) -> str:
    if not iso:
        return "—"
    d = _to_date(iso)
    return f"{d.day}/{d.month}"


def kpi(f: dict) -> dict:
    """KPI-kort til data.json['kpis']['ftp']."""
    if not f or f.get("ftpW") is None:
        return {"value": "—", "unit": "W", "sub": "Ingen FTP i plan.json", "color": NEUTRAL}
    parts = []
    if f.get("wkg") is not None:
        parts.append(f"{str(f['wkg']).replace('.', ',')} W/kg")
    if f.get("phaseTarget"):
        parts.append(f"mål {f['phaseTarget']} ({f.get('phase') or ''})".replace(" ()", ""))
    if f.get("nextTest"):
        parts.append(f"test {_dk(f['nextTest'])}")
    return {"value": str(f["ftpW"]), "unit": "W", "sub": " · ".join(parts) or "FTP", "color": f["color"]}
