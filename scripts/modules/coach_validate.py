# -*- coding: utf-8 -*-
"""
Coach v2 — mekanisk validering af modellens strukturerede svar.

Reglerne er kode, ikke prosa:
  1. Alle tal i alle tekstfelter skal findes i konteksten (tolerance: afrunding
     til 1 decimal eller til helt tal). Datoer, klokkeslæt, ugenumre og brøker
     (5/7) ignoreres. Små heltal 0..SMALL_INT_OK (antal pas, dage, "to hårde")
     accepteres altid — de er tællinger, ikke målinger.
  2. oneThing.action må ikke være et TSS-status-resumé ("x procent af ugens TSS").
  3. warnings[].action.edit må kun pege på entry-id'er der findes i konteksten
     (og templateId på kataloget) — ellers fjernes advarslen (blød fejl).
  2b. oneThing.action må kun nævne ERG når dagens pas er på cykel.
  4. Længder klippes (oneThing.action 140, why 160); levels normaliseres.

validate(answer, ctx) -> (ok, errors, cleaned). ok=False => svaret kasseres og
forrige beholdes (som QA-gaten altid har gjort).
"""
import re

SMALL_INT_OK = 7
ACTION_MAX = 140
WHY_MAX = 160
MAX_WARNINGS = 3
LEVELS = ('info', 'warn', 'act')
EDIT_ACTIONS = ('move', 'cancel', 'swap_template')

ERG_RE = re.compile(r"\berg\b", re.I)


def _today_has_bike(ctx):
    """True hvis mindst ét af dagens pas er på cykel (eller disc er ukendt)."""
    sess = ((ctx or {}).get("today") or {}).get("sessions") or []
    if not sess:
        return True  # ingen viden -> ingen afvisning
    return any((x.get("disc") or "bike") == "bike" for x in sess)


TSS_STATUS_RE = re.compile(r"procent af ugens tss|% af ugens tss|af ugens tss er i hus", re.I)

# Mønstre der fjernes FØR tal-udtræk: ISO-dato, d/m(-yyyy), hh:mm, "uge 36", brøker 5/7,
# "1. sep"-datoer, "kl. 6"
_STRIP = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}(?:-\d{2,4})?\b"),
    re.compile(r"\b\d{1,2}[:.]\d{2}\b(?=\s*(?:$|[^\d%]))"),  # 06:35 / 06.35
    re.compile(r"\buge\s*\d+\b", re.I),
    re.compile(r"\b\d{1,2}\.\s*(?:jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)\w*", re.I),
    re.compile(r"\bkl\.?\s*\d{1,2}\b", re.I),
    re.compile(r"\b(?:19|20)\d{2}\b"),  # årstal
]
_NUM = re.compile(r"(?<![\w/])[-−]?\d+(?:[.,]\d+)?(?![\w/])")


def numbers_in_text(text):
    """Alle tal i en tekst som float — efter at datoer/klokkeslæt/ugenr er fjernet."""
    if not text:
        return []
    t = str(text)
    for rx in _STRIP:
        t = rx.sub(" ", t)
    out = []
    for m in _NUM.finditer(t):
        s = m.group(0).replace("−", "-").replace(",", ".")
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def _walk(obj, acc):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        acc.add(float(obj))
    elif isinstance(obj, str):
        for v in numbers_in_text(obj):
            acc.add(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk(v, acc)


def context_numbers(ctx):
    """Alle numeriske værdier i konteksten (inkl. tal i strenge som '60 min')."""
    acc = set()
    _walk(ctx, acc)
    return acc


def number_allowed(v, ctx_nums):
    v = float(v)
    if v == int(v) and 0 <= v <= SMALL_INT_OK:
        return True
    for c in ctx_nums:
        if abs(v - c) < 1e-9:
            return True
        if abs(v - round(c, 1)) < 0.051:
            return True
        if v == int(v) and int(round(c)) == int(v):
            return True
        if abs(v) == abs(c):  # fortegn skrevet som "minus 0,7" eller "−0,7"
            return True
    return False


def _text_fields(answer):
    """(sti, tekst) for alle fritekstfelter i svaret."""
    out = []
    ot = answer.get("oneThing") or {}
    out.append(("oneThing.action", ot.get("action")))
    out.append(("oneThing.why", ot.get("why")))
    for k in ("training", "body", "habits"):
        out.append((f"{k}.text", (answer.get(k) or {}).get("text")))
    out.append(("bigPicture", answer.get("bigPicture")))
    out.append(("weekFocus", answer.get("weekFocus")))
    for i, w in enumerate(answer.get("warnings") or []):
        out.append((f"warnings[{i}].message", (w or {}).get("message")))
        lab = ((w or {}).get("action") or {}).get("label") if isinstance((w or {}).get("action"), dict) else None
        out.append((f"warnings[{i}].action.label", lab))
    return [(p, t) for p, t in out if t]


def _entry_ids(ctx):
    try:
        from . import coach_context
        return coach_context.entry_ids(ctx)
    except Exception:
        return set()


def _catalog_ids(ctx):
    return {w.get("id") for w in (ctx.get("catalog") or []) if w.get("id")}


def validate(answer, ctx, *, require_week_focus=False):
    """Returnerer (ok, errors, cleaned). errors er en liste af strenge (dansk)."""
    errors, notes = [], []
    if not isinstance(answer, dict):
        return False, ["svaret er ikke et objekt"], None
    a = {k: v for k, v in answer.items()}
    ctx_nums = context_numbers(ctx)

    # 1. Tal
    for path, text in _text_fields(a):
        bad = [v for v in numbers_in_text(text) if not number_allowed(v, ctx_nums)]
        if bad:
            errors.append(f"{path}: tal ikke i konteksten: {', '.join(_fmt(v) for v in bad)}")

    # 2. oneThing
    ot = a.get("oneThing") if isinstance(a.get("oneThing"), dict) else {}
    action = (ot.get("action") or "").strip()
    if not action:
        errors.append("oneThing.action mangler")
    elif TSS_STATUS_RE.search(action):
        errors.append("oneThing.action er et TSS-status-resumé, ikke en handling")
    if ERG_RE.search(action) and not _today_has_bike(ctx):
        errors.append("oneThing.action nævner ERG, men dagens pas er ikke på cykel — ERG gælder kun trainer-pas")
    a["oneThing"] = {"action": action[:ACTION_MAX], "why": (ot.get("why") or "").strip()[:WHY_MAX] or None}

    # 3. Sektioner
    for k in ("training", "body", "habits"):
        sec = a.get(k) if isinstance(a.get(k), dict) else {}
        txt = (sec.get("text") or "").strip()
        if not txt:
            errors.append(f"{k}.text mangler")
        refs = [float(r) for r in (sec.get("refs") or []) if isinstance(r, (int, float)) and not isinstance(r, bool)]
        a[k] = {"text": txt, "refs": refs}
    a["bigPicture"] = (a.get("bigPicture") or "").strip() or None
    if not a["bigPicture"]:
        errors.append("bigPicture mangler")
    wf = (a.get("weekFocus") or "")
    wf = str(wf).strip().split("\n")[0].strip().strip('"').strip("'").rstrip(".")[:120] if wf else None
    a["weekFocus"] = wf or None
    if require_week_focus and not wf:
        errors.append("weekFocus mangler (søndag/mandag)")

    # 4. Warnings
    ids = _entry_ids(ctx)
    cat = _catalog_ids(ctx)
    cleaned_w = []
    for w in (a.get("warnings") or []):
        if not isinstance(w, dict) or not (w.get("message") or "").strip():
            continue
        lvl = str(w.get("level") or "info").lower()
        if lvl not in LEVELS:
            lvl = "warn" if lvl in ("warning", "critical") else "info"
        act = w.get("action") if isinstance(w.get("action"), dict) else None
        if act:
            edit = act.get("edit") if isinstance(act.get("edit"), dict) else None
            ok_edit = bool(edit) and edit.get("action") in EDIT_ACTIONS
            if ok_edit and edit.get("entryId") and edit["entryId"] not in ids:
                ok_edit = False
                notes.append(f"advarsel '{w.get('message')[:40]}': ukendt entryId {edit.get('entryId')} — handling fjernet")
            if ok_edit and edit.get("action") in ("move", "cancel", "swap_template") and not edit.get("entryId"):
                ok_edit = False
            if ok_edit and edit.get("templateId") and cat and edit["templateId"] not in cat:
                ok_edit = False
                notes.append(f"advarsel: ukendt templateId {edit.get('templateId')} — handling fjernet")
            if ok_edit:
                act = {"label": (act.get("label") or "Åbn i planen")[:40],
                       "edit": {k: edit[k] for k in ("action", "entryId", "date", "toDate", "templateId") if edit.get(k)}}
            else:
                act = None
        cleaned_w.append({"type": (w.get("type") or "coach")[:32], "level": lvl,
                          "message": w["message"].strip()[:200], "action": act})
    rank = {"act": 0, "warn": 1, "info": 2}
    cleaned_w.sort(key=lambda w: rank[w["level"]])
    a["warnings"] = cleaned_w[:MAX_WARNINGS]
    a["validationNotes"] = notes or None

    return (not errors), errors, (a if not errors else None)


def _fmt(v):
    return str(int(v)) if float(v) == int(v) else str(v).replace(".", ",")


def merge_warnings(rule_warnings, ai_warnings, limit=MAX_WARNINGS):
    """Regelbaserede advarsler (update_kpi) får action: null og flettes med
    AI-advarsler. Højeste level først; max `limit`. Dubletter på type fjernes
    (regel-advarslen vinder)."""
    lvl_map = {"critical": "act", "warn": "warn", "info": "info"}
    rank = {"act": 0, "warn": 1, "info": 2}
    out, seen = [], set()
    for w in (rule_warnings or []):
        if not isinstance(w, dict) or not w.get("message"):
            continue
        lvl = lvl_map.get(str(w.get("level")).lower(), str(w.get("level")).lower())
        if lvl not in rank:
            lvl = "warn"
        out.append({"type": w.get("type") or "rule", "level": lvl, "message": w["message"],
                    "action": None, "source": "rule"})
        seen.add(w.get("type"))
    for w in (ai_warnings or []):
        if not isinstance(w, dict) or not w.get("message"):
            continue
        if w.get("type") in seen:
            continue
        out.append({"type": w.get("type") or "coach", "level": w.get("level", "info"),
                    "message": w["message"], "action": w.get("action"), "source": "ai"})
    out.sort(key=lambda w: rank.get(w["level"], 2))
    return out[:limit]
