# -*- coding: utf-8 -*-
"""
Soendagsbrief — Fast as Fifty (27/11-2026).

Svarer paa to spoergsmaal soendag morgen, foer ugen begynder:
  1. Hvad er planlagt i den kommende uge?
  2. Skal der laves noget om?

Spoergsmaal 2 er det vigtigste. Friel-gaten kender ugens problemer, men den
staar paa dashboardets Plan-fane, hvor man kun ser den hvis man aabner den.
En uge der slet ikke er lagt endnu taeller ogsaa som "noget at lave om" — det
er den hyppigste aarsag til at en uge ender som improvisation.

Rene funktioner. Ingen netvaerk, ingen fil-I/O.
"""
from datetime import date, timedelta

try:
    from . import programs as _programs
    from . import friel as _friel
except ImportError:                       # tests importerer som top-level
    import programs as _programs
    import friel as _friel

DISC_NAVN = {"Ride": "cykel", "VirtualRide": "cykel", "Run": "løb", "Swim": "svøm",
             "WeightTraining": "styrke", "Hike": "vandring", "Walk": "gang",
             "Gravel": "cykel", "GravelRide": "cykel", "MountainBike": "cykel"}
# Flag-navne som de staar i friel.py -> kort dansk, saa beskeden kan laeses paa
# en laasskaerm uden at aabne noget.
FLAG_DA = {
    "max_runs": "for mange løbedage", "consecutive_runs": "løb to dage i træk",
    "vo2_missing": "ingen VO2-stimulus", "vo2_excess": "for mange VO2-pas",
    "missing_recovery": "mangler R&R", "tsb_floor": "TSB under gulvet",
    "ctl_ramp": "CTL stiger for hurtigt", "hard_per_week": "over 2 hårde pas",
    "hard_spacing": "hårde pas for tæt", "easy_days_min": "for få lette dage",
    "z5_per_session": "for meget Z5 i ét pas",
}


def next_monday(today):
    """Mandagen i den KOMMENDE uge. Koeres soendag, saa det er i morgen."""
    d = date.fromisoformat(today) if isinstance(today, str) else today
    return d + timedelta(days=(7 - d.weekday()) % 7 or 7)


def week_plan(plan, athlete, monday):
    """{uge, blockType, phase, purpose, tssTarget, pas[], discipliner{}, dage}
    for ugen der starter `monday`. None hvis ugen ligger uden for programmet."""
    prog = _programs.active_program(plan, athlete, today=monday.isoformat())
    if not prog:
        return None
    wk = next((w for w in (prog.get("weeks") or []) if w.get("start") == monday.isoformat()), None)
    if wk is None:
        return None
    pas, discipliner, dage = [], {}, 0
    for d in (plan.get("athletes", {}).get(athlete, {}).get("days") or []):
        dd = date.fromisoformat(d["date"])
        if not (0 <= (dd - monday).days < 7):
            continue
        dage += 1
        for e in d.get("entries") or []:
            wo = e.get("workout")
            if not wo:
                continue
            t = wo.get("type")
            navn = DISC_NAVN.get(t, (t or "pas").lower())
            discipliner[navn] = discipliner.get(navn, 0) + 1
            pas.append({"date": d["date"], "navn": wo.get("name") or navn,
                        "disc": navn, "load": _friel.entry_load(e)})
    return {"week": wk.get("week"), "isoWeek": monday.isocalendar()[1],
            "start": monday.isoformat(), "blockType": wk.get("blockType"),
            "phase": wk.get("phase"), "purpose": wk.get("purpose"),
            "note": wk.get("note"), "tssTarget": wk.get("tssTarget"),
            "keySession": wk.get("keySession"), "pas": pas,
            "discipliner": discipliner, "dage": dage,
            "haarde": [p for p in pas if p["load"] == "haard"]}


def week_flags(plan, athlete, week_no, today=None):
    """Friel-flag der gaelder netop den uge, med kort dansk tekst."""
    try:
        fl = _friel.validate(plan, athlete=athlete, today=today)
    except Exception:
        return []
    ud = []
    for f in fl:
        if f.get("week") != week_no or f.get("historic"):
            continue
        ud.append({"rule": f["rule"], "level": f["level"],
                   "kort": FLAG_DA.get(f["rule"], f["rule"]), "msg": f.get("msg")})
    return ud


def build(plan, athlete="kennet", today=None):
    """Push-payload til soendagsbriefen, eller None hvis der intet er at sige."""
    today = today or date.today().isoformat()
    monday = next_monday(today)
    w = week_plan(plan, athlete, monday)
    if not w:
        return None
    flags = week_flags(plan, athlete, w["week"], today=monday.isoformat())

    if w["dage"] == 0:
        titel = f"KU{w['isoWeek']} er ikke lagt endnu"
        krop = (f"{w['blockType'] or '?'}"
                + (f" · {w['tssTarget']} TSS" if w["tssTarget"] else "")
                + (f". {w['purpose']}" if w["purpose"] else "")).strip()
        return {"title": titel, "body": krop[:220] or "Ingen dage i planen.",
                "tag": "fast50-week", "url": "./#plan", "athlete": athlete,
                "flags": flags, "dage": 0}

    dele = [f"{n} {navn}" for navn, n in
            sorted(w["discipliner"].items(), key=lambda kv: -kv[1])]
    titel = (f"KU{w['isoWeek']} · {w['blockType'] or '?'}"
             + (f" · {w['tssTarget']} TSS" if w["tssTarget"] else ""))
    krop = f"{len(w['pas'])} pas: " + ", ".join(dele) + "."
    if w["haarde"]:
        krop += " Hårdt: " + ", ".join(p["navn"] for p in w["haarde"][:2]) + "."
    if flags:
        krop += f" {len(flags)} at rette: " + ", ".join(f["kort"] for f in flags[:2]) + "."
    else:
        krop += " Intet at rette."
    return {"title": titel, "body": krop[:220], "tag": "fast50-week",
            "url": "./#plan", "athlete": athlete, "flags": flags, "dage": w["dage"]}
