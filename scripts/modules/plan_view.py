# -*- coding: utf-8 -*-
"""
Plan-view-generator — Fast as Fifty fase 2.

Beregner det afledte lag som plan.html/eva.html viser, men aldrig selv må
beregne (Friel-logik bor KUN i Python, jf. PROJECT_KICKOFF.md):

  data/plan_view.json:
    generated       ISO-timestamp
    inputsHash      sha256 af (plan.json-indhold + seed) — hash-guard
    kennet.seed     {date, ctl, atl} — LIVE Intervals-fitness ved generering
    kennet.projection  [{d, ctl, tsb}] dagligt fra seed til planslut
    kennet.weeks    [{week, projEndCtl, deviation, flags:[...]}]
                    deviation = projektion minus ctlTarget (INFO, ikke flag —
                    target er løst styringsmål, jf. Kennets beslutning 7/7)
    kennet.flags    fuld flagliste fra friel.validate

Selve planstrukturen (uger, dage, workouts) læser siderne direkte fra
plan.json — dette modul dublerer den ikke.

Kaldes fra update_kpi.py med live fitness; falder tilbage til
plan.json fitnessSeed.current hvis fitness mangler.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from . import friel


def inputs_hash(plan_raw: str, seed_ctl, seed_atl, seed_date: str) -> str:
    key = f"{plan_raw}|{round(float(seed_ctl), 1)}|{round(float(seed_atl), 1)}|{seed_date}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def compute(plan: dict, seed_ctl, seed_atl, seed_date: str) -> dict:
    """Ren beregning — ingen I/O. Testes direkte."""
    flags = friel.validate(plan, seed_ctl=seed_ctl, seed_atl=seed_atl,
                           seed_date=seed_date)
    proj = friel.project_fitness(plan, seed_ctl, seed_atl, seed_date)

    projection = [{"d": d, "ctl": v["ctl"], "tsb": v["tsb"]}
                  for d, v in sorted(proj.items())]

    week_end_ctl = {}
    plan_start = plan["program"]["start"]
    from datetime import date as _date
    ps = _date.fromisoformat(plan_start)
    for d_iso, v in sorted(proj.items()):
        w = (_date.fromisoformat(d_iso) - ps).days // 7 + 1
        if 1 <= w <= plan["program"]["totalWeeks"]:
            week_end_ctl[w] = v["ctl"]

    weeks = []
    for wm in plan["weeks"]:
        w = wm["week"]
        proj_end = week_end_ctl.get(w)
        deviation = (round(proj_end - wm["ctlTarget"], 1)
                     if proj_end is not None and wm.get("ctlTarget") is not None
                     else None)
        weeks.append({
            "week": w,
            "projEndCtl": proj_end,
            "deviation": deviation,
            "flags": [f for f in flags if f["week"] == w],
        })

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kennet": {
            "seed": {"date": seed_date,
                     "ctl": round(float(seed_ctl), 1),
                     "atl": round(float(seed_atl), 1)},
            "projection": projection,
            "weeks": weeks,
            "flags": flags,
        },
    }


def update_plan_view(fitness: Optional[dict]) -> bool:
    """
    Hentes/skrives via GitHub Contents API (samme mønster som data.json).
    Hash-guard: skriver KUN når plan.json eller fitness-seed er ændret,
    så 10-minutters-cron ikke støjer med tomme commits.
    Returnerer True hvis der blev skrevet.
    """
    from .github import gh_get, gh_put
    from datetime import date as _date

    _sha_plan, plan_raw = gh_get("data/plan.json")
    if not plan_raw:
        print("  plan_view: kunne ikke hente plan.json — springer over")
        return False
    plan = json.loads(plan_raw)

    if fitness and fitness.get("ctl") is not None:
        seed_ctl, seed_atl = fitness["ctl"], fitness["atl"]
        seed_date = str(_date.today())
    else:
        cur = plan.get("fitnessSeed", {}).get("current", {})
        seed_ctl, seed_atl = cur.get("ctl"), cur.get("atl")
        seed_date = cur.get("date")
        if seed_ctl is None:
            print("  plan_view: ingen fitness-seed — springer over")
            return False

    new_hash = inputs_hash(plan_raw, seed_ctl, seed_atl, seed_date)

    sha_view, view_raw = gh_get("data/plan_view.json")
    if view_raw:
        try:
            if json.loads(view_raw).get("inputsHash") == new_hash:
                print("  plan_view: uændret (hash-guard) — springer over")
                return False
        except (ValueError, AttributeError):
            pass

    view = compute(plan, seed_ctl, seed_atl, seed_date)
    view["inputsHash"] = new_hash

    gh_put("data/plan_view.json", sha_view,
           json.dumps(view, ensure_ascii=False, indent=1),
           f"plan_view opdateret {seed_date}")
    print(f"  plan_view: skrevet (seed CTL {seed_ctl}, "
          f"{len(view['kennet']['flags'])} flags)")
    return True
