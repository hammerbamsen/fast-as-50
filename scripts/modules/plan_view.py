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
    kennet.flags    fuld flagliste fra friel.validate (+ plan_coherence)
    kennet.fueling  carb/væske/natrium-mål for Médoc + Stelvio (standarddefaults,
                    jf. Kennets beslutning — bygges nu, kalibreres senere m. Martin)

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
from . import plan_coherence
from . import fueling


def inputs_hash(plan_raw: str, seed_ctl, seed_atl, seed_date: str,
                readiness=None, adapt_sig="", coherence_sig="") -> str:
    key = f"{plan_raw}|{round(float(seed_ctl), 1)}|{round(float(seed_atl), 1)}|{seed_date}"
    if readiness:
        key += f"|{readiness}"   # T1: readiness-skift skal trigge omskrivning
    if adapt_sig:
        key += f"|{adapt_sig}"   # T3: nyt adaptations-forslag trigger omskrivning
    if coherence_sig:
        key += f"|{coherence_sig}"   # T5: nyt kohærens-flag trigger omskrivning
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def compute(plan: dict, seed_ctl, seed_atl, seed_date: str,
            readiness=None, current_week=None, adaptation=None, coherence=None) -> dict:
    """Ren beregning — ingen I/O. Testes direkte.

    T1: readiness/current_week videreføres til Friel-validering. Default None
    -> hidtidig adfærd.
    T3: adaptation-dict (fra modules.adaptation.compute_adaptation) skrives
    uændret ind under kennet.adaptation når givet.
    T5: coherence er en pre-beregnet flag-liste fra
    plan_coherence.coherence_flags (samme {week,rule,level,msg}-format som
    friel-flags) — flettes ind i den samlede flags-liste når givet. Default
    None -> hidtidig adfærd, fuldt bagudkompatibelt.
    Fase 2: kennet.fueling sættes altid — statiske standarddefaults for
    Médoc/Stelvio (fueling.all_race_targets()), uafhængig af plan-indhold.
    """
    flags = friel.validate(plan, seed_ctl=seed_ctl, seed_atl=seed_atl,
                           seed_date=seed_date,
                           readiness=readiness, current_week=current_week)
    if coherence:
        flags = flags + coherence
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

    kennet = {
        "seed": {"date": seed_date,
                 "ctl": round(float(seed_ctl), 1),
                 "atl": round(float(seed_atl), 1)},
        "projection": projection,
        "weeks": weeks,
        "flags": flags,
        "fueling": fueling.all_race_targets(),
    }
    if adaptation is not None:
        kennet["adaptation"] = adaptation

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kennet": kennet,
    }


def update_plan_view(fitness: Optional[dict], wellness: Optional[dict] = None,
                     activities: Optional[list] = None) -> bool:
    """
    Hentes/skrives via GitHub Contents API (samme mønster som data.json).
    Hash-guard: skriver KUN når plan.json, fitness-seed, readiness, adaptations-
    signaturen eller kohærens-signaturen er ændret, så 10-minutters-cron ikke
    støjer med tomme commits.
    Returnerer True hvis der blev skrevet.
    """
    from .github import gh_get, gh_put
    from datetime import date as _date
    from . import adaptation as _adaptation

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

    # T1: morgen-readiness ud fra dagens HRV vs 7d-snit + søvn (samme signaler
    # update_kpi allerede henter). Beregnes FØR hash-guarden, så et readiness-
    # skift (fx dårlig søvn -> LOW) selv trigger en omskrivning af plan_view.
    readiness = current_week = None
    if wellness:
        readiness = friel.readiness_band(
            wellness.get("hrv"), wellness.get("hrv_avg"), wellness.get("sleep_avg"))
        try:
            ps = _date.fromisoformat(plan["program"]["start"])
            cw = (_date.today() - ps).days // 7 + 1
            if 1 <= cw <= plan["program"]["totalWeeks"]:
                current_week = cw
        except (KeyError, ValueError):
            pass

    # T3: detektér missede pas + byg forslag (fase-guardet). Deterministisk
    # signatur indgår i hash-guarden, så et NYT forslag selv trigger en
    # omskrivning — men uændret tilstand ikke støjer.
    adapt = None
    if activities is not None:
        try:
            adapt = _adaptation.compute_adaptation(
                plan, activities, _date.today(), readiness=readiness)
        except Exception as e:
            print(f"  plan_view: adaptation sprang over ({e})")
            adapt = None
    adapt_sig = _adaptation.signature(adapt) if adapt else ""

    # T5 — plan-kohærens: aktivitets-disciplin uden for planen i historiske
    # uger (jf. Wales-eksempel: "ingen cykel" i plan, men logget cykeltur).
    coherence = None
    if activities is not None:
        try:
            coherence = plan_coherence.coherence_flags(plan, activities)
        except Exception as e:
            print(f"  plan_view: coherence sprang over ({e})")
            coherence = None
    coherence_sig = plan_coherence.signature(coherence) if coherence else ""

    new_hash = inputs_hash(plan_raw, seed_ctl, seed_atl, seed_date,
                           readiness, adapt_sig=adapt_sig, coherence_sig=coherence_sig)

    sha_view, view_raw = gh_get("data/plan_view.json")
    if view_raw:
        try:
            if json.loads(view_raw).get("inputsHash") == new_hash:
                print("  plan_view: uændret (hash-guard) — springer over")
                return False
        except (ValueError, AttributeError):
            pass

    view = compute(plan, seed_ctl, seed_atl, seed_date,
                   readiness=readiness, current_week=current_week,
                   adaptation=adapt, coherence=coherence)
    view["inputsHash"] = new_hash
    if readiness:
        view["kennet"]["readiness"] = readiness

    gh_put("data/plan_view.json", sha_view,
           json.dumps(view, ensure_ascii=False, indent=1),
           f"plan_view opdateret {seed_date}")
    print(f"  plan_view: skrevet (seed CTL {seed_ctl}, "
          f"{len(view['kennet']['flags'])} flags)")
    return True
