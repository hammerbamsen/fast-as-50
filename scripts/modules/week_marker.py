# -*- coding: utf-8 -*-
"""
Heldags-ugemarkering i Outlook — Fast as Fifty (27/11-2026).

Een heldagsbegivenhed pr. programuge, saa kalenderen selv siger hvad det er
for en uge: blockType, sted, ugens formaal og noegletal. Formaalet er at kunne
planlaegge arbejde og rejser uden at aabne dashboardet — en lejruge eller en
race-uge skal kunne ses i kalenderen.

Markeringen er IKKE en traeningsbegivenhed: kategori "Ugeplan", showAs free,
isAllDay. Den maa ikke blokere tid eller forveksles med et pas. Kategorien
hedder bevidst ikke "Traeningsuge": build_workouts' sletteregel rammer alt med
"ning" i kategori eller emne, og en race-uge hvis formaal naevner "B-loeb"
ville ogsaa ryge. Derfor ogsaa en heldagsvagt i den regel.

`fingerprint()` er naoglen til at kunne koere synken ofte uden at skrive:
indeholder markeringen samme fingeraftryk som planens uge, er der intet at
gore. Uden det ville hver koersel slette og genoprette 40 begivenheder.

Rene funktioner. Netvaerk ligger i .github/workflows/scripts/sync_week_markers.py.
"""
import hashlib
from datetime import date, timedelta

# Kategorien maa IKKE indeholde "ning": build_workouts.outlook_delete_by_date
# sletter alt hvor kategori eller emne indeholder "ning" (fra "Træning"), og
# "Træningsuge" ville derfor blive ryddet af traeningssynken.
KATEGORI = "Ugeplan"
EMNE_MAX = 120
FELTER = ("blockType", "phase", "location", "ctlTarget", "tssTarget",
          "purpose", "note", "keySession")


def _iso(start):
    return date.fromisoformat(start).isocalendar()[1]


def fingerprint(wk):
    """Kort hash af de felter markeringen viser. Aendrer et forslag ugens
    formaal eller blockType, aendrer fingeraftrykket sig — og kun da."""
    raw = "|".join(str(wk.get(k) or "") for k in FELTER)
    kv = wk.get("quota") or {}
    raw += "|" + ",".join(f"{k}={kv[k]}" for k in sorted(kv))
    raw += "|" + ",".join(str(t.get("label") or t) for t in (wk.get("travel") or []))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def subject(wk):
    """'KU11 · CAMP Mallorca — Lejr #1: volumen og aerob base'"""
    dele = [f"KU{_iso(wk['start'])}", wk.get("blockType") or "?"]
    sted = wk.get("location")
    if sted and sted.lower() not in ("gentofte", ""):
        dele.append(sted)
    hoved = " · ".join(dele)
    form = (wk.get("purpose") or "").strip()
    if form:
        # foerste saetning af formaalet — resten staar i body
        kort = form.split(". ")[0].rstrip(".")
        hoved = f"{hoved} — {kort}"
    return hoved[:EMNE_MAX]


def body(wk):
    """Detaljerne. Sidste linje er fingeraftrykket, som synken laeser igen."""
    linjer = []
    nøgle = [("Fase", wk.get("phase")), ("Blok", wk.get("blockType")),
             ("Sted", wk.get("location")), ("CTL-mål", wk.get("ctlTarget")),
             ("TSS-mål", wk.get("tssTarget"))]
    linjer += [f"{k}: {v}" for k, v in nøgle if v not in (None, "")]
    kv = wk.get("quota") or {}
    if kv:
        linjer.append("Kvote: " + ", ".join(f"{k} {kv[k]}" for k in sorted(kv)))
    if wk.get("purpose"):
        linjer += ["", "Formål:", wk["purpose"]]
    if wk.get("keySession"):
        linjer += ["", "Nøglepas: " + str(wk["keySession"])]
    if wk.get("note"):
        linjer += ["", "Note:", str(wk["note"])]
    rejser = [t.get("label") or str(t) for t in (wk.get("travel") or [])]
    if rejser:
        linjer += ["", "Rejse: " + ", ".join(rejser)]
    løb = [r.get("name") for r in (wk.get("races") or []) if r.get("name")]
    if løb:
        linjer += ["", "Løb: " + ", ".join(løb)]
    linjer += ["", f"— Fast as Fifty · uge {wk.get('week')} · sync:{fingerprint(wk)}"]
    return "\n".join(linjer)


def event(wk):
    """Graph-payload. Heldags: start mandag, end naeste mandag (eksklusiv)."""
    start = date.fromisoformat(wk["start"])
    return {
        "subject": subject(wk),
        "isAllDay": True,
        "showAs": "free",
        "start": {"dateTime": f"{start.isoformat()}T00:00:00", "timeZone": "Europe/Copenhagen"},
        "end": {"dateTime": f"{(start + timedelta(days=7)).isoformat()}T00:00:00",
                "timeZone": "Europe/Copenhagen"},
        "body": {"contentType": "text", "content": body(wk)},
        "categories": [KATEGORI],
    }


def fingerprint_i_event(ev):
    """Laes fingeraftrykket ud af en eksisterende markering. None hvis det
    mangler (fx en markering oprettet i haanden)."""
    tekst = ((ev or {}).get("body") or {}).get("content") or ""
    for stykke in tekst.replace("\r", "").split("\n"):
        if "sync:" in stykke:
            return stykke.split("sync:", 1)[1].strip()[:10] or None
    return None


def er_markering(ev):
    """Er begivenheden en af vores? Kategori foerst, ellers emnet."""
    if KATEGORI in ((ev or {}).get("categories") or []):
        return True
    subj = ((ev or {}).get("subject") or "")
    return subj.startswith("KU") and " · " in subj and bool((ev or {}).get("isAllDay"))


def plan_weeks(plan, program_id=None, fra=None, til=None):
    """Programmets uger som markeringer skal daekke.

    `fra`/`til` er datoer (ISO) der afgraenser vinduet — standard er hele
    programmet. Uger uden startdato springes over.
    """
    progs = (plan.get("programs") or {})
    prog = progs.get(program_id) if program_id else None
    if prog is None:
        prog = max((p for p in progs.values() if p.get("start")),
                   key=lambda p: p["start"], default=None)
    if not prog:
        return []
    ud = []
    for w in (prog.get("weeks") or []):
        if not w.get("start"):
            continue
        if fra and w["start"] < fra:
            continue
        if til and w["start"] > til:
            continue
        ud.append(dict(w, programId=prog.get("id")))
    return ud
