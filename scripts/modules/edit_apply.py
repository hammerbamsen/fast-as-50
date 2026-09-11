# -*- coding: utf-8 -*-
"""
Fast as Fifty — server-side redigering af plan.json fra plan.html.

Flow:
  1. plan.html sender repository_dispatch { entryId, action, params, requestId }
  2. plan-edit.yml → apply_edit.py → denne funktion
  3. apply_edit() validerer via Friel, muterer plan.json, orkestrerer:
     plan.json commit → Intervals event(s) → Outlook event(s)
     → Word master snapshot → skriv edit_result.json
  4. plan.html poller edit_result.json på requestId

Alle actions arbejder på entry-niveau — undtagen set_zones og strength_log
(blok 8: 3 felter efter styrkepas -> athletes.kennet.strengthLog[dato]), som
hører til atleten og ikke rører Intervals/Outlook, og apply_proposal/
reject_proposal (blok 9: entryId 'proposal:<id>' -> data/proposals/<id>.json,
alle set_day-changes i én simulation + check_week pr. uge). Ved mutation af én entry på en dag,
slettes ALLE den dags Intervals+Outlook events og genskabes fra plan.json
— sikreste mønster (samme som build_workouts.py).
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from typing import Optional

from . import friel
from . import zones as zone_math


# -- Friel-gate ---------------------------------------------------------------

def _simulate_mutation(plan: dict, action: str, entry_id: str,
                       params: Optional[dict],
                       athlete: str = "kennet") -> tuple[dict, str, str]:
    """
    Returnerer (simuleret_plan, dato_der_ændres, evt_ekstra_dato).
    Muterer IKKE input-plan. Understøtter både 'kennet' og 'eva'.
    """
    sim = copy.deepcopy(plan)

    # Særtilfælde: restore rammer hele planen, ikke en enkelt entry
    if action == "restore_from_commit":
        # Klienten sender enten 'source_commit' (foretrukket) eller 'restored_plan'.
        # I workflow-orkestratoren hentes den fulde plan fra commit'et.
        if not (params.get("restored_plan") or params.get("source_commit")):
            raise ValueError("restore_from_commit kræver 'source_commit' eller 'restored_plan'")
        if not params.get("restored_plan"):
            # apply_edit.py (orkestrator) skal have hentet planen først
            raise ValueError("orkestrator skal hente restored_plan fra source_commit før _simulate_mutation")
        restored = json.loads(params["restored_plan"]) if isinstance(params["restored_plan"], str) else params["restored_plan"]
        # Bevar programMeta (arkiv, upcoming) og fitnessSeed så de ikke rulles tilbage utilsigtet
        if "programMeta" in sim:
            restored["programMeta"] = sim["programMeta"]
        if "fitnessSeed" in sim:
            restored["fitnessSeed"] = sim["fitnessSeed"]
        return restored, "restore", ""

    # Særtilfælde: zoner hører til atleten, ikke til en entry. Håndteres før
    # entry-opslaget, præcis som restore_from_commit.
    if action == "set_zones":
        z = sim["athletes"][athlete].get("zones")
        if not z:
            raise ValueError(f"Atlet {athlete!r} har ingen zones-blok")
        sim["athletes"][athlete]["zones"] = zone_math.set_zones(
            z,
            threshold_sec=params.get("thresholdSec"),
            ftp_w=params.get("ftpW"),
        )
        # FTP-historik (blok 13): ny FTP -> post i ftpHistory, så Krop-fanen
        # kan vise progression mod fasemålet. Uændret FTP skriver intet.
        if params.get("ftpW"):
            from . import ftp_track
            ftp_track.record(sim, int(params["ftpW"]), date.today(), "set_zones", athlete)
        return sim, "zones", ""

    # Særtilfælde (blok 8): styrke-log efter pas. Hører til atleten, ikke til
    # en entry — entryId er 'log:YYYY-MM-DD'. Ingen Friel-implikationer.
    if action == "strength_log":
        d_iso, rec = strength_log_record(entry_id, params)
        log = sim["athletes"][athlete].setdefault("strengthLog", {})
        log[d_iso] = rec                      # samme dato overskrives
        return sim, "strength_log", ""

    # Særtilfælde (blok 10): 14-dages styrke-check-in. entryId 'chk:YYYY-MM-DD'
    # (søndagen), params legs/upper 0/1. Skriver strengthCheckin[dato] og
    # ruller strengthProgression frem (recovery-uge udskyder effectiveFrom).
    if action == "strength_checkin":
        from . import strength_progression as _sp
        d_iso, rec = strength_checkin_record(entry_id, params)
        ath = sim["athletes"][athlete]
        ath.setdefault("strengthCheckin", {})[d_iso] = rec
        ath["strengthProgression"] = _sp.apply_checkin(
            ath.get("strengthProgression"), d_iso, bool(rec["legs"]), bool(rec["upper"]),
            ath.get("days") or [])
        return sim, "strength_checkin", ""

    # Særtilfælde (blok 9): forslag. entryId er 'proposal:<id>'; forslaget
    # læses fra data/proposals/<id>.json (eller params['proposal'] — samme
    # struktur — så offline-anvendelse og tests går gennem præcis denne vej).
    # Alle set_day-changes anvendes i ÉN simulation; gaten i apply_edit tager
    # Friel + bike_library.check_week() pr. berørt uge.
    if action in ("apply_proposal", "reject_proposal"):
        from . import proposals as _props
        pid = _props.pid_from_entry_id(entry_id)
        prop = params.get("proposal") or _props.load(pid)
        _props.validate(prop)
        if prop["id"] != pid:
            raise ValueError(f"Forslag-id {prop['id']!r} matcher ikke entryId {entry_id!r}")
        if prop["status"] != "pending" and not params.get("allow_decided"):
            raise ValueError(f"Forslag {pid!r} er allerede afgjort ({prop['status']})")
        if action == "reject_proposal":
            return sim, "reject_proposal", ""
        sim, dates = _props.apply_changes(sim, prop["changes"], athlete)
        # primary_date bærer ALLE datoer (liste) — apply_edit pakker dem ud.
        return sim, dates, ""

    ath = sim["athletes"][athlete]

    # Find entry
    src_day = src_entry = None
    for d in ath["days"]:
        for e in d["entries"]:
            if e.get("id") == entry_id:
                src_day, src_entry = d, e
                break
        if src_entry:
            break
    if not src_entry:
        raise ValueError(f"Entry-id {entry_id!r} ikke fundet for atlet {athlete!r}")

    extra_date = ""

    if action == "adjust":
        # params: {name?, type?, moving_time?, description?, note?}
        wo = src_entry.get("workout") or {}
        for k in ("name", "type", "description"):
            if k in params:
                wo[k] = params[k]
        if "moving_time" in params:
            wo["moving_time"] = int(params["moving_time"])
        src_entry["workout"] = wo
        if "note" in params:
            src_entry["note"] = params["note"]

    elif action == "toggle_done":
        # Marker/aflys 'gennemført' — ingen Friel-implikationer, kun status
        from datetime import date as _date
        current = bool(src_entry.get("done"))
        src_entry["done"] = not current
        if src_entry["done"]:
            src_entry["done_at"] = _date.today().isoformat()
        else:
            src_entry.pop("done_at", None)

    elif action == "toggle_optional":
        # Valgfrit pas: bliver stående i Intervals/Outlook (med "(valgfri)" i
        # navnet), men tæller ikke med i CTL-projektionen — friel viser det
        # konservative scenarie hvor passet springes over.
        if src_entry.get("optional"):
            src_entry.pop("optional", None)
        else:
            src_entry["optional"] = True

    elif action == "swap_template":
        # params: {template_id, note?}. template_id kan være et id fra
        # workout_library.json ELLER et kælderpas-id fra bike_library.json
        # (Plan-fanens "Skift pas" for cykelpas, 6/9-2026).
        tpl = _find_template(params["template_id"])
        if tpl["type"] is None:
            src_entry["workout"] = None
            src_entry.pop("libraryId", None)
        else:
            src_entry["workout"] = {
                "name": tpl["name"], "type": tpl["type"],
                "moving_time": tpl["moving_time"],
                "description": tpl["description"],
            }
            if tpl.get("workout_doc"):
                src_entry["workout"]["workout_doc"] = tpl["workout_doc"]
            if tpl.get("libraryId"):
                src_entry["libraryId"] = tpl["libraryId"]
            else:
                src_entry.pop("libraryId", None)
        if "note" in params:
            src_entry["note"] = params["note"]

    elif action == "cancel":
        src_entry["workout"] = None
        src_entry["note"] = params.get("note", "Aflyst — hviledag")

    elif action == "move":
        # params: {target_date, mode: 'swap'|'replace'}
        target_date = params["target_date"]
        mode = params.get("mode", "swap")
        # find måldag
        dst_day = None
        for d in ath["days"]:
            if d["date"] == target_date:
                dst_day = d
                break
        if not dst_day:
            # ny dag — indsæt struktur
            dst_day = {"date": target_date, "entries": []}
            ath["days"].append(dst_day)
            ath["days"].sort(key=lambda d: d["date"])
        if mode == "swap" and len(src_day["entries"]) == 1:
            # Enkelt-pas-kildedag: byt hele dagenes indhold, som hidtil.
            src_day["entries"], dst_day["entries"] = dst_day["entries"], src_day["entries"]
        elif mode == "swap":
            # Flerdages-kildedag: flyt KUN den valgte entry over. Øvrige pas
            # på kildedagen skal IKKE rives med — dette var buggen 13/7 2026,
            # hvor hele entries-listen blev byttet og Svøm fulgte med Styrke.
            src_idx = next(i for i, e in enumerate(src_day["entries"]) if e is src_entry)
            dst_day["entries"].append(src_day["entries"].pop(src_idx))
        else:  # replace
            dst_day["entries"] = src_day["entries"]
            src_day["entries"] = []
        extra_date = target_date

    else:
        raise ValueError(f"Ukendt action: {action!r}")

    return sim, src_day["date"], extra_date


STRENGTH_NOTE_MAX = 140


def strength_checkin_record(entry_id: str, params: Optional[dict]) -> tuple[str, dict]:
    """Validerer et check-in (blok 10): entryId 'chk:YYYY-MM-DD' (eller
    params['date']), legs og upper hver 0/1. Record {legs, upper, at}."""
    params = params or {}
    raw = entry_id or ""
    d_raw = raw[4:] if raw.startswith("chk:") else params.get("date")
    try:
        d_iso = date.fromisoformat(str(d_raw)[:10]).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"strength_checkin kræver entryId 'chk:YYYY-MM-DD' (fik {entry_id!r})")
    out = {}
    for k in ("legs", "upper"):
        v = params.get(k)
        if isinstance(v, bool):
            v = int(v)
        if v not in (0, 1, "0", "1"):
            raise ValueError(f"strength_checkin: {k} skal være 0 eller 1")
        out[k] = int(v)
    out["at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return d_iso, out


def strength_log_record(entry_id: str, params: Optional[dict]) -> tuple[str, dict]:
    """Validerer et styrke-log-kald og returnerer (dato, record).

    entry_id 'log:YYYY-MM-DD' (dato kan alternativt stå i params['date']).
    params: rpe 1-10 (heltal), complete 0/1 (alle runder × reps), note ≤ 140
    tegn, template (template-id, valgfri). Record: {rpe, complete, note,
    template, at} hvor at er ISO UTC."""
    params = params or {}
    raw = entry_id or ""
    d_raw = raw[4:] if raw.startswith("log:") else params.get("date")
    try:
        d_iso = date.fromisoformat(str(d_raw)[:10]).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"strength_log kræver entryId 'log:YYYY-MM-DD' (fik {entry_id!r})")
    try:
        rpe = int(params.get("rpe"))
    except (TypeError, ValueError):
        raise ValueError("strength_log: rpe skal være et heltal 1-10")
    if not 1 <= rpe <= 10:
        raise ValueError(f"strength_log: rpe {rpe} uden for 1-10")
    comp = params.get("complete")
    if isinstance(comp, bool):
        comp = int(comp)
    if comp not in (0, 1, "0", "1"):
        raise ValueError("strength_log: complete skal være 0 eller 1")
    note = str(params.get("note") or "").strip()
    if len(note) > STRENGTH_NOTE_MAX:
        raise ValueError(f"strength_log: note må højst være {STRENGTH_NOTE_MAX} tegn ({len(note)})")
    tpl = params.get("template")
    return d_iso, {
        "rpe": rpe,
        "complete": int(comp),
        "note": note,
        "template": str(tpl) if tpl else None,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _find_template(tid: str) -> dict:
    """Slå template op i data/workout_library.json (lokal på Actions checkout).
    Findes id'et ikke der, prøves data/bike_library.json (kælderpas) — så
    Plan-fanen kan skifte et cykelpas til et andet fra biblioteket. Resultatet
    bærer da `libraryId` + `workout_doc` (bike_library.to_intervals)."""
    from pathlib import Path
    lib_path = Path(__file__).resolve().parent.parent.parent / "data" / "workout_library.json"
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    for t in lib["templates"]:
        if t["id"] == tid:
            return t
    try:
        from . import bike_library
        wo = bike_library.to_intervals(tid)
    except KeyError:
        raise ValueError(f"Template-id {tid!r} findes ikke i workout_library.json eller bike_library.json")
    return {"id": tid, "libraryId": tid, **wo}


def gate_check(plan: dict, sim_plan: dict, confirmed_warn: bool = False,
               athlete: str = "kennet") -> dict:
    """
    Friel-gate. Kører fuld validate på simuleret plan.
    For 'eva' bruges kun strukturregler (ingen fitness/CTL — hun er ikke på Intervals).
    """
    def _key(f):
        return (f["week"], f["rule"], f["msg"])

    if athlete == "kennet":
        seed = plan.get("fitnessSeed", {}).get("current", {})
        kwargs = dict(seed_ctl=seed.get("ctl"), seed_atl=seed.get("atl"),
                      seed_date=seed.get("date"))
        before = {_key(f) for f in friel.validate(plan, **kwargs)
                  if not f.get("historic")}
        after_flags = friel.validate(sim_plan, **kwargs)
    else:
        # Eva: kun strukturregler (structural_flags for eva-atleten)
        before = {_key(f) for f in friel.validate(plan, athlete=athlete)
                  if not f.get("historic")}
        after_flags = friel.validate(sim_plan, athlete=athlete)

    new_flags = [f for f in after_flags
                 if _key(f) not in before and not f.get("historic")]

    hard_new = [f for f in new_flags if f["level"] == "HARD"]
    warn_new = [f for f in new_flags if f["level"] == "WARN"]

    if hard_new:
        return {"status": "reject", "flags": hard_new,
                "msg": "Afvist: " + "; ".join(f["msg"] for f in hard_new)}
    if warn_new and not confirmed_warn:
        return {"status": "warn", "flags": warn_new,
                "msg": "Advarsel: " + "; ".join(f["msg"] for f in warn_new)}
    return {"status": "ok", "flags": [], "msg": "Godkendt"}


def suggest_move_alternatives(plan_json_raw: str, entry_id: str,
                              athlete: str = "kennet",
                              window_days: int = 7) -> dict:
    """
    Prøver at flytte entry til hver dato ±window_days og returnerer OK-alternativer.
    Ren funktion — muterer ikke.
    """
    from datetime import date as _date, timedelta
    plan = json.loads(plan_json_raw)
    ath = plan["athletes"][athlete]

    # Find src-dato
    src_date = None
    for d in ath["days"]:
        for e in d["entries"]:
            if e.get("id") == entry_id:
                src_date = d["date"]
                break
        if src_date: break
    if not src_date:
        return {"error": f"Entry {entry_id} ikke fundet for {athlete}"}

    src_dt = _date.fromisoformat(src_date)
    alternatives = []
    for offset in range(-window_days, window_days+1):
        if offset == 0: continue
        target_dt = src_dt + timedelta(days=offset)
        target_iso = target_dt.isoformat()
        try:
            sim, _, _ = _simulate_mutation(plan, "move", entry_id,
                                           {"target_date": target_iso, "mode": "swap"},
                                           athlete=athlete)
            gate = gate_check(plan, sim, confirmed_warn=False, athlete=athlete)
            alternatives.append({
                "date": target_iso,
                "offset": offset,
                "status": gate["status"],
                "msg": gate.get("msg", ""),
            })
        except Exception as e:
            alternatives.append({"date": target_iso, "offset": offset,
                                 "status": "error", "msg": str(e)})

    # Sortér: OK først (efter afstand fra src), så warn, så reject
    order = {"ok": 0, "warn": 1, "reject": 2, "error": 3}
    alternatives.sort(key=lambda a: (order.get(a["status"], 9), abs(a["offset"])))
    return {"alternatives": alternatives, "src_date": src_date, "entry_id": entry_id}


# -- Orkestrering -------------------------------------------------------------

def apply_edit(plan_json_raw: str, action: str, entry_id: str,
               params: dict, confirmed_warn: bool = False,
               athlete: str = "kennet") -> dict:
    """
    Ren funktion — muterer ikke I/O. Returnerer:
      { status, new_plan_raw, dates_changed, gate, request_ts, athlete }
    """
    plan = json.loads(plan_json_raw)
    sim_plan, primary_date, extra_date = _simulate_mutation(
        plan, action, entry_id, params or {}, athlete=athlete)
    if action == "strength_log":
        # Ingen Friel-gate: loggen ændrer ingen pas, kun atletens strengthLog.
        gate = {"status": "ok", "flags": [], "msg": "Styrkelog gemt"}
    elif action == "strength_checkin":
        gate = {"status": "ok", "flags": [], "msg": "Check-in gemt"}
    elif action == "reject_proposal":
        gate = {"status": "ok", "flags": [], "msg": "Forslag afvist"}
    else:
        gate = None
        if action == "apply_proposal":
            # Kælderreglen (CLAUDE.md §3) pr. berørt uge FØR Friel — brud er
            # altid reject (aldrig warn), så den kan ikke bekræftes væk.
            from . import proposals as _props
            broken = _props.check_weeks(sim_plan, primary_date, athlete)
            if broken:
                msgs = [f"{lbl}: {'; '.join(w)}" for lbl, w in broken]
                gate = {"status": "reject", "msg": "Afvist (kælderregel): " + " | ".join(msgs),
                        "flags": [{"week": lbl, "rule": "bike_library", "level": "HARD", "msg": m}
                                  for lbl, ws in broken for m in ws]}
        if gate is None:
            gate = gate_check(plan, sim_plan, confirmed_warn=confirmed_warn, athlete=athlete)

    # set_zones/strength_log/reject_proposal rører ingen dage. Uden dette ville
    # orkestratoren forsøge intervals_delete_date("zones") og outlook_sync_date(...).
    if action in ("set_zones", "strength_log", "strength_checkin", "reject_proposal"):
        dates = []
    elif action == "apply_proposal":
        dates = list(primary_date)            # alle datoer i forslaget
    else:
        dates = [primary_date] + ([extra_date] if extra_date else [])
    result = {
        "status": gate["status"],
        "gate": gate,
        "dates_changed": dates,
        "athlete": athlete,
        "request_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if action in ("apply_proposal", "reject_proposal"):
        from . import proposals as _props
        result["proposal_id"] = _props.pid_from_entry_id(entry_id)
    if gate["status"] == "ok":
        result["new_plan_raw"] = json.dumps(sim_plan, ensure_ascii=False, indent=2) + "\n"
    return result
