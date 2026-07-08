# -*- coding: utf-8 -*-
"""
T3 — Adaptiv re-planlægning (Fast as Fifty).

Detekterer missede pas i de seneste dage ved at matche planlagte entries i
plan.json mod faktiske Intervals-aktiviteter, og foreslår ÉN konkret
justering af det næste hårde pas (Z4/Z5/VO2):

  - readiness LOW  -> foreslå hviledag (cancel)
  - ellers         -> foreslå nedjustering til Z2 (swap_template)

Forslaget anvendes ALDRIG automatisk — det vises som banner i plan.html og
går gennem den normale plan-edit-workflow (Friel-gate + Historik-rollback).

Fase-guard (træningsekspert-krav): i RECOVERY/TAPER/RACE-uger gives INTET
forslag — missede pas dér er ofte planlagt reduktion.

Kun for 'kennet' (Eva har ikke Intervals — anden logik).

Ren beregning — ingen I/O. Kaldes fra plan_view.update_plan_view med
aktiviteter hentet i update_kpi, og on-demand via apply_edit-action
'suggest_adaptation'.
"""
from datetime import date, timedelta

from . import friel

# Tærskler (jf. designbeslutning 7/7-2026)
MISSED_7D_TRIGGER = 2    # >= 2 missede pas på 7 dage
MISSED_10D_TRIGGER = 3   # ELLER >= 3 på 10 dage
WINDOW_DAYS = 10
MATCH_TIME_RATIO = 0.30  # aktivitet tæller som gennemført ved >= 30 % af planlagt tid
LOOKAHEAD_DAYS = 7       # næste hårde pas søges i de kommende 7 dage

# Samme disciplin-gruppering som sessions.py (bevidst dubleret — modulet
# skal kunne testes uden Intervals-afhængigheder)
TYPE_MAP = {
    'Run': 'run', 'TrailRun': 'run', 'VirtualRun': 'run', 'IndoorRun': 'run',
    'Ride': 'bike', 'VirtualRide': 'bike', 'MountainBike': 'bike',
    'Cyclocross': 'bike', 'Gravel': 'bike', 'GravelRide': 'bike',
    'Swim': 'swim', 'OpenWaterSwim': 'swim',
    'WeightTraining': 'strength', 'Workout': 'strength', 'Strength': 'strength',
    'Hike': 'hike', 'Walk': 'hike',
}

# Z2-erstatning pr. disciplin (template-id'er fra data/workout_library.json)
Z2_TEMPLATE = {'run': 'lob-z2-45', 'bike': 'cykel-z2-60', 'swim': 'svom-1500'}


def _disc(wo_type):
    return TYPE_MAP.get(wo_type or '', 'free')


def _is_hard(wo):
    """Z4/Z5/VO2-pas — kandidat til nedjustering."""
    if not wo:
        return False
    if friel._is_vo2(wo):
        return True
    txt = ((wo.get("name") or "") + " " + (wo.get("description") or "")).lower()
    return "z4" in txt.split("z3")[0] or " z4" in txt or " z5" in txt or "z5" in (wo.get("name") or "").lower()


def _travel_dates(plan):
    """Alle rejsedage (ikke kun Mallorca) — missede pas her tæller ikke."""
    dates = set()
    for t in plan.get("travel", []):
        try:
            s = date.fromisoformat(t["start"])
            e = date.fromisoformat(t.get("end", t["start"]))
        except (KeyError, ValueError):
            continue
        d = s
        while d <= e:
            dates.add(d.isoformat())
            d += timedelta(days=1)
    return dates


def detect_missed(plan, activities, today, window_days=WINDOW_DAYS):
    """
    Missede pas i [today - window_days ; today - 1] (i dag tæller ikke —
    dagen er ikke slut). Match: aktivitet i samme disciplin på dagen ±1 dag
    med moving_time >= 30 % af planlagt. Hver aktivitet bruges højst én gang.

    Returnerer liste af {date, entry_id, name, type} sorteret efter dato.
    """
    if isinstance(today, str):
        today = date.fromisoformat(today)
    lo = today - timedelta(days=window_days)
    travel = _travel_dates(plan)

    planned = []
    for d in plan["athletes"]["kennet"]["days"]:
        try:
            dd = date.fromisoformat(d["date"])
        except ValueError:
            continue
        if not (lo <= dd < today) or d["date"] in travel:
            continue
        for e in d["entries"]:
            wo = e.get("workout")
            if wo and wo.get("type"):
                planned.append({"date": d["date"], "entry_id": e.get("id"),
                                "name": wo.get("name", ""), "type": wo["type"],
                                "disc": _disc(wo["type"]),
                                "moving_time": wo.get("moving_time") or 0})

    # Aktivitets-pulje: (dato, disc, moving_time), forbruges grådigt
    pool = []
    for a in (activities or []):
        dt = (a.get("start_date_local") or "")[:10]
        if not dt:
            continue
        pool.append({"date": dt, "disc": _disc(a.get("type")),
                     "moving_time": a.get("moving_time") or 0, "used": False})

    missed = []
    for p in sorted(planned, key=lambda x: x["date"]):
        pd = date.fromisoformat(p["date"])
        candidates = []
        for act in pool:
            if act["used"] or act["disc"] != p["disc"]:
                continue
            try:
                ad = date.fromisoformat(act["date"])
            except ValueError:
                continue
            gap = abs((ad - pd).days)
            if gap <= 1 and (p["moving_time"] <= 0
                             or act["moving_time"] >= MATCH_TIME_RATIO * p["moving_time"]):
                candidates.append((gap, act))
        if candidates:
            candidates.sort(key=lambda c: c[0])   # tættest dato først
            candidates[0][1]["used"] = True
        else:
            missed.append({"date": p["date"], "entry_id": p["entry_id"],
                           "name": p["name"], "type": p["type"]})
    return missed


def suggest(plan, missed, today, readiness=None):
    """
    Bygger adaptations-dict ud fra missed-listen. Deterministisk (ingen
    timestamps) — indgår i plan_views hash-guard.
    """
    if isinstance(today, str):
        today = date.fromisoformat(today)

    m7 = [m for m in missed
          if date.fromisoformat(m["date"]) >= today - timedelta(days=7)]
    triggered = len(m7) >= MISSED_7D_TRIGGER or len(missed) >= MISSED_10D_TRIGGER

    out = {
        "triggered": triggered,
        "missed7": len(m7),
        "missed10": len(missed),
        "missed": missed,
        "suggestion": None,
        "phase_guard": None,
    }
    if not triggered:
        return out

    # Fase-guard: intet forslag i recovery/taper/race-uger
    weeks_meta = {w["week"]: w for w in plan.get("weeks", [])}
    try:
        ps = date.fromisoformat(plan["program"]["start"])
        cw = (today - ps).days // 7 + 1
    except (KeyError, ValueError):
        cw = None
    phase = friel._phase(weeks_meta, cw) if cw else ""
    if phase in ("RECOVERY", "TAPER", "RACE"):
        out["phase_guard"] = (f"Uge {cw} er {phase} — missede pas her er ofte "
                              "planlagt reduktion; ingen justering foreslås.")
        return out

    # Find næste hårde pas i de kommende LOOKAHEAD_DAYS dage
    hi = today + timedelta(days=LOOKAHEAD_DAYS)
    target = None
    for d in sorted(plan["athletes"]["kennet"]["days"], key=lambda x: x["date"]):
        try:
            dd = date.fromisoformat(d["date"])
        except ValueError:
            continue
        if not (today <= dd <= hi):
            continue
        # Måldagens uge må heller ikke være recovery/taper/race
        tw = (dd - ps).days // 7 + 1 if cw else None
        if tw and friel._phase(weeks_meta, tw) in ("RECOVERY", "TAPER", "RACE"):
            continue
        for e in d["entries"]:
            if _is_hard(e.get("workout")):
                target = {"date": d["date"], "entry": e}
                break
        if target:
            break

    if not target:
        out["phase_guard"] = "Ingen hårde pas i de kommende 7 dage at justere."
        return out

    e = target["entry"]
    wo = e["workout"]
    reason = (f"{len(m7)} missede pas de sidste 7 dage"
              if len(m7) >= MISSED_7D_TRIGGER
              else f"{len(missed)} missede pas de sidste 10 dage")

    if readiness == "LOW":
        sug = {"suggested_action": "cancel",
               "params": {"note": "Hviledag — tilpasning efter missede pas (readiness LOW)"},
               "label": f"Aflys \u201d{wo.get('name','')}\u201d og tag en hviledag"}
    else:
        tpl = Z2_TEMPLATE.get(_disc(wo.get("type")))
        if tpl:
            sug = {"suggested_action": "swap_template",
                   "params": {"template_id": tpl,
                              "note": "Nedjusteret til Z2 — tilpasning efter missede pas"},
                   "label": f"Nedjustér \u201d{wo.get('name','')}\u201d til Z2"}
        else:
            sug = {"suggested_action": "cancel",
                   "params": {"note": "Hviledag — tilpasning efter missede pas"},
                   "label": f"Aflys \u201d{wo.get('name','')}\u201d og tag en hviledag"}

    sug.update({"entry_id": e.get("id"), "date": target["date"],
                "name": wo.get("name", ""), "reason": reason})
    if friel._is_vo2(wo):
        sug["vo2_note"] = ("Passet er ugens VO2-stimulus — overvej at flytte det "
                           "i stedet for at nedjustere (VO2 bør ikke udgå to "
                           "build-uger i træk).")
    out["suggestion"] = sug
    return out


def compute_adaptation(plan, activities, today, readiness=None):
    """Wrapper: detektion + forslag i ét kald."""
    missed = detect_missed(plan, activities, today)
    return suggest(plan, missed, today, readiness=readiness)


def signature(adapt):
    """Kompakt, deterministisk signatur til plan_views hash-guard."""
    if not adapt:
        return ""
    sug = adapt.get("suggestion") or {}
    return (f"{int(adapt.get('triggered', False))}:"
            f"{','.join(m['date'] for m in adapt.get('missed', []))}"
            f">{sug.get('entry_id','')}:{sug.get('suggested_action','')}")
