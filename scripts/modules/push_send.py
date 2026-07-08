# -*- coding: utf-8 -*-
"""
U2 — Web Push: ren logik til daglig påmindelse.

Ingen I/O, ingen netværk — testes direkte af CI (X4). Selve afsendelsen
(pywebpush) og repo-læsning bor i scripts/send_push.py.

Designvalg:
- Kun pas udløser en notifikation. Hviledage sender INTET (undgår spam).
- Én notifikation pr. atlet pr. dag, med dagens pas samlet i teksten.
- Notifikationen bærer dagens konkrete pas ("I dag: Løb Z2 45 min") — værdi,
  ikke bare "husk at træne" (jf. træningsekspert-review).
"""
from datetime import date


def workouts_for(plan: dict, athlete: str, day_iso: str) -> list:
    """Navne på dagens pas for en atlet (tom liste = hviledag/ingen)."""
    ath = plan.get("athletes", {}).get(athlete)
    if not ath:
        return []
    for d in ath.get("days", []):
        if d.get("date") == day_iso:
            return [e["workout"]["name"]
                    for e in d.get("entries", [])
                    if e.get("workout") and e["workout"].get("name")]
    return []


def build_daily_message(plan: dict, athlete: str, day_iso: str) -> dict | None:
    """
    Returnerer en push-payload-dict, eller None hvis der intet er at sende
    (hviledag). Payloadet matcher det sw.js's push-handler forventer.
    """
    names = workouts_for(plan, athlete, day_iso)
    if not names:
        return None
    body = " + ".join(names)
    url = "eva.html" if athlete == "eva" else "./"
    return {
        "title": f"I dag: {body}",
        "body": "Fast as Fifty — dagens pas",
        "tag": "fast50-daily",     # samme tag => erstatter gårsdagens, spammer ikke
        "url": url,
        "athlete": athlete,
    }


def is_dead_status(status_code: int) -> bool:
    """404/410 fra push-service => subscription er død og skal fjernes."""
    return status_code in (404, 410)


def prune_subscriptions(subs: list, dead_endpoints: set) -> list:
    """Fjerner døde subscriptions ud fra endpoint."""
    return [s for s in subs if s.get("endpoint") not in dead_endpoints]


def subs_for_athlete(subs: list, athlete: str) -> list:
    return [s for s in subs if s.get("athlete") == athlete]


def upsert_subscription(subs: list, new_sub: dict, today: str | None = None) -> list:
    """
    Tilføjer eller opdaterer en subscription (dedup på endpoint).
    Bevarer 'added'-dato hvis den fandtes; sætter den ellers til today.
    """
    today = today or str(date.today())
    endpoint = new_sub.get("endpoint")
    out = []
    replaced = False
    for s in subs:
        if s.get("endpoint") == endpoint:
            merged = dict(new_sub)
            merged["added"] = s.get("added", today)
            out.append(merged)
            replaced = True
        else:
            out.append(s)
    if not replaced:
        nn = dict(new_sub)
        nn.setdefault("added", today)
        out.append(nn)
    return out
