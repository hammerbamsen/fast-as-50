# -*- coding: utf-8 -*-
"""
Plan-kohærens-tjek — Fast as Fifty (Fase 1 backlog).

Fanger uger hvor planen og de faktiske aktiviteter modsætter hinanden —
konkret: en aktivitets-disciplin optræder i en uge UDEN at være en del af
ugens plan overhovedet (jf. fundament-reviewets Wales-eksempel: ugen var
markeret "ingen cykel", men fik alligevel en cykeltur).

Bevidst simpelt første snit: sammenligner discipliner (run/bike/swim/
strength/hike), ikke enkelt-pas. Kun HISTORISKE uger (<= actualsThroughWeek)
vurderes — fremtidige uger har naturligt ingen aktivitetsdata endnu.

Disciplin-mapping bevidst dubleret fra adaptation.py/sessions.py (samme
begrundelse: modulet skal kunne testes uden Intervals-afhængigheder).

Ren beregning — ingen I/O. Kaldes fra plan_view.compute() når activities
er givet.
"""
from datetime import date

MIN_ACTIVITY_SECONDS = 600  # 10 min — filtrerer gps-test/stop-glemt-pings fra

TYPE_MAP = {
    'Run': 'run', 'TrailRun': 'run', 'VirtualRun': 'run', 'IndoorRun': 'run',
    'Ride': 'bike', 'VirtualRide': 'bike', 'MountainBike': 'bike',
    'Cyclocross': 'bike', 'Gravel': 'bike', 'GravelRide': 'bike',
    'Swim': 'swim', 'OpenWaterSwim': 'swim',
    'WeightTraining': 'strength', 'Workout': 'strength', 'Strength': 'strength',
    'Hike': 'hike', 'Walk': 'hike',
}


def _disc(wo_type):
    return TYPE_MAP.get(wo_type or '', 'free')


def _week_no(d_iso, plan_start):
    return (date.fromisoformat(d_iso) - plan_start).days // 7 + 1


def coherence_flags(plan, activities, athlete="kennet"):
    """Returnerer flags i samme format som friel.py: {week, rule, level, msg}.

    Regel 'plan_actual_mismatch' (WARN): en disciplin optræder blandt de
    faktiske aktiviteter i en historisk uge, men ingen af ugens planlagte
    pas har den disciplin. 'free'/ukendte typer ignoreres (for meget støj
    fra fx GPS-test eller manuelle log-poster uden type).
    """
    flags = []
    if not activities:
        return flags
    try:
        plan_start = date.fromisoformat(plan["program"]["start"])
        total_weeks = plan["program"]["totalWeeks"]
    except (KeyError, ValueError):
        return flags

    actuals_through = plan.get("athletes", {}).get(athlete, {}).get("actualsThroughWeek", 0)
    days = plan.get("athletes", {}).get(athlete, {}).get("days", [])

    planned_disc_by_week = {}
    for d in days:
        try:
            w = _week_no(d["date"], plan_start)
        except (KeyError, ValueError):
            continue
        if not 1 <= w <= total_weeks:
            continue
        for e in d.get("entries", []):
            wo = e.get("workout")
            if wo and wo.get("type"):
                planned_disc_by_week.setdefault(w, set()).add(_disc(wo["type"]))

    actual_disc_by_week = {}
    for a in activities:
        dt = (a.get("start_date_local") or "")[:10]
        if not dt:
            continue
        try:
            w = _week_no(dt, plan_start)
        except ValueError:
            continue
        if not 1 <= w <= total_weeks or w > actuals_through:
            continue
        if (a.get("moving_time") or 0) < MIN_ACTIVITY_SECONDS:
            continue
        disc = _disc(a.get("type"))
        if disc == "free":
            continue
        actual_disc_by_week.setdefault(w, set()).add(disc)

    for w, actual_set in sorted(actual_disc_by_week.items()):
        planned_set = planned_disc_by_week.get(w, set())
        extra = sorted(actual_set - planned_set)
        if extra:
            names = ", ".join(extra)
            flags.append({
                "week": w, "rule": "plan_actual_mismatch", "level": "WARN",
                "msg": f"Logget {names}-aktivitet i uge {w}, men ugens plan indeholder ikke {names}",
            })
    return flags


def signature(flags):
    """Kompakt, deterministisk signatur til plan_views hash-guard."""
    return "|".join(f"{f['week']}:{f['rule']}" for f in flags)
