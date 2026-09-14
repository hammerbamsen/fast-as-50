# -*- coding: utf-8 -*-
"""
Forslag (proposals) til plan.json — blok 9 (9/9-2026).

Et forslag er en fil `data/proposals/<id>.json` med en liste af `changes`.
I denne blok findes kun `set_day`: dagens entries erstattes af forslagets
entries (eksisterende `done`-entries på datoen bevares altid).

Kontrakt (se blok9-spec §1):
  {id, createdAt, createdBy, title, note, summary[], status, decidedAt,
   result, changes[{date, action:'set_day', entries[{workout, libraryId?,
   templateId?, note?}]}]}
  status: pending | accepted | rejected | applied-offline

Anvendelse går ALTID gennem edit_apply.apply_edit(action='apply_proposal')
— både live (apply_edit.py via plan-edit.yml) og offline (`python3 -m
modules.proposals apply-offline <id>` fra scripts/). Ingen særvej: samme
simulation, samme Friel-gate, samme bike_library.check_week().

Ren logik uden netværk. Fil-I/O kun i load/save/list og i CLI'en.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from . import bike_library
from . import programs as _programs

ROOT = Path(__file__).resolve().parent.parent.parent
PROPOSALS_DIR = ROOT / "data" / "proposals"
STATUSES = ("pending", "accepted", "rejected", "applied-offline")
ENTRY_ID_PREFIX = "proposal:"


# -- fil-I/O ------------------------------------------------------------------

def proposal_path(pid: str, root: Optional[Path] = None) -> Path:
    if not pid or "/" in pid or "\\" in pid or pid.startswith("."):
        raise ValueError(f"Ugyldigt forslag-id {pid!r}")
    return (root or PROPOSALS_DIR) / f"{pid}.json"


def load(pid: str, root: Optional[Path] = None) -> dict:
    p = proposal_path(pid, root)
    if not p.exists():
        raise ValueError(f"Forslag {pid!r} findes ikke ({p.name})")
    prop = json.loads(p.read_text(encoding="utf-8"))
    validate(prop)
    return prop


def save(prop: dict, root: Optional[Path] = None) -> Path:
    validate(prop)
    p = proposal_path(prop["id"], root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps(prop), encoding="utf-8")
    return p


def dumps(prop: dict) -> str:
    return json.dumps(prop, ensure_ascii=False, indent=2) + "\n"


def list_all(root: Optional[Path] = None) -> list[dict]:
    d = root or PROPOSALS_DIR
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            prop = json.loads(p.read_text(encoding="utf-8"))
            validate(prop)
        except Exception:
            continue                       # defekt fil må ikke vælte pipelinen
        out.append(prop)
    return out


def list_pending(root: Optional[Path] = None) -> list[dict]:
    return [p for p in list_all(root) if p.get("status") == "pending"]


def pid_from_entry_id(entry_id: str) -> str:
    """'proposal:<id>' -> '<id>'."""
    raw = entry_id or ""
    if not raw.startswith(ENTRY_ID_PREFIX) or len(raw) <= len(ENTRY_ID_PREFIX):
        raise ValueError(f"apply/reject_proposal kræver entryId 'proposal:<id>' (fik {entry_id!r})")
    return raw[len(ENTRY_ID_PREFIX):]


# -- validering ---------------------------------------------------------------

def validate(prop: dict) -> None:
    if not isinstance(prop, dict):
        raise ValueError("Forslag skal være et objekt")
    for k in ("id", "title", "status", "changes"):
        if k not in prop:
            raise ValueError(f"Forslag mangler feltet {k!r}")
    if prop["status"] not in STATUSES:
        raise ValueError(f"Ukendt status {prop['status']!r} (tilladt: {', '.join(STATUSES)})")
    if not isinstance(prop["changes"], list):
        raise ValueError("changes skal være en liste")
    seen = set()
    seen_tgt = set()
    for ch in prop["changes"]:
        if ch.get("action") == "set_week_targets":
            # 14/9-2026: CTL-rekalibrering — ændrer ctlTarget/tssTarget på en programuge.
            pid_, wk = ch.get("programId"), ch.get("week")
            if not isinstance(pid_, str) or not pid_:
                raise ValueError("set_week_targets: programId mangler")
            if not isinstance(wk, int) or isinstance(wk, bool) or wk < 1:
                raise ValueError(f"set_week_targets: ugyldig week {wk!r}")
            if (pid_, wk) in seen_tgt:
                raise ValueError(f"set_week_targets: uge {wk} i {pid_} optræder to gange")
            seen_tgt.add((pid_, wk))
            if not any(isinstance(ch.get(k), (int, float)) and not isinstance(ch.get(k), bool)
                       for k in ("ctlTarget", "tssTarget")):
                raise ValueError(f"set_week_targets uge {wk}: ctlTarget eller tssTarget skal angives")
            continue
        if ch.get("action") != "set_day":
            raise ValueError(f"Ukendt change-action {ch.get('action')!r} — kun set_day og set_week_targets understøttes")
        try:
            d_iso = date.fromisoformat(str(ch.get("date"))).isoformat()
        except (TypeError, ValueError):
            raise ValueError(f"Ugyldig dato i change: {ch.get('date')!r}")
        if d_iso in seen:
            raise ValueError(f"Datoen {d_iso} optræder to gange i changes")
        seen.add(d_iso)
        if not isinstance(ch.get("entries"), list):
            raise ValueError(f"set_day {d_iso}: entries skal være en liste")
        for e in ch["entries"]:
            wo = e.get("workout")
            if wo is not None and not (isinstance(wo, dict) and wo.get("name") and wo.get("type")):
                raise ValueError(f"set_day {d_iso}: workout kræver name + type")


# -- id-generering ------------------------------------------------------------

def all_entry_ids(plan: dict) -> set:
    return {e.get("id")
            for a in (plan.get("athletes") or {}).values() if isinstance(a, dict)
            for d in a.get("days") or []
            for e in d.get("entries") or [] if e.get("id")}


def new_entry_id(d_iso: str, name: str, existing: set) -> str:
    """8 hex-tegn (samme form som planens øvrige id'er), deterministisk ud fra
    dato + navn, med tæller ved kollision."""
    n = 0
    while True:
        eid = hashlib.sha1(f"{d_iso}|{name}|{n}".encode("utf-8")).hexdigest()[:8]
        if eid not in existing:
            existing.add(eid)
            return eid
        n += 1


def _same_workout(a: dict, b: dict) -> bool:
    """Samme pas = samme libraryId, ellers samme navn+type. Bruges til at
    genbruge entry-id når et forslag kun ændrer note på et uændret pas."""
    if a.get("libraryId") or b.get("libraryId"):
        return a.get("libraryId") == b.get("libraryId")
    wa, wb = a.get("workout") or {}, b.get("workout") or {}
    return bool(wa) and wa.get("name") == wb.get("name") and wa.get("type") == wb.get("type")


# -- anvendelse (ren) ---------------------------------------------------------

def apply_changes(plan: dict, changes: list, athlete: str = "kennet") -> tuple[dict, list]:
    """Returnerer (ny_plan, datoer). Muterer IKKE input.

    set_day: dagens entries = [eksisterende done-entries] + forslagets entries.
    Id'er: et uændret pas (samme libraryId / navn+type) beholder sit id,
    ellers genereres et nyt 8-hex id der er unikt i hele planen."""
    sim = copy.deepcopy(plan)
    ath = sim["athletes"][athlete]
    days = {d["date"]: d for d in ath["days"]}
    existing_ids = all_entry_ids(sim)
    dates = []
    for ch in changes:
        if ch.get("action") == "set_week_targets":
            _apply_week_targets(sim, ch)
            continue                     # ingen dage berørt -> intet at synke
        d_iso = date.fromisoformat(str(ch["date"])).isoformat()
        day = days.get(d_iso)
        if day is None:
            day = {"date": d_iso, "entries": []}
            ath["days"].append(day)
            days[d_iso] = day
        old_entries = list(day.get("entries") or [])
        kept = [e for e in old_entries if e.get("done")]
        reusable = [e for e in old_entries if not e.get("done")]
        new_entries = []
        for spec in ch.get("entries") or []:
            e = {k: copy.deepcopy(v) for k, v in spec.items() if k != "id"}
            e.setdefault("workout", None)
            match = next((o for o in reusable if _same_workout(o, e)), None)
            if match is not None:
                reusable.remove(match)
                e = {"id": match["id"], **e}
            else:
                name = (e.get("workout") or {}).get("name") or "fri"
                e = {"id": new_entry_id(d_iso, name, existing_ids), **e}
            new_entries.append(e)
        day["entries"] = kept + new_entries
        dates.append(d_iso)
    ath["days"].sort(key=lambda d: d["date"])
    return sim, dates


def _apply_week_targets(sim: dict, ch: dict) -> dict:
    """Muterer sim['programs'][programId]['weeks'][week] med ctlTarget/tssTarget."""
    progs = sim.get("programs")
    prog = progs.get(ch["programId"]) if isinstance(progs, dict) else None
    if not isinstance(prog, dict):
        raise ValueError(f"set_week_targets: program {ch['programId']!r} findes ikke i plan.programs")
    wk = next((w for w in (prog.get("weeks") or []) if w.get("week") == ch["week"]), None)
    if wk is None:
        raise ValueError(f"set_week_targets: uge {ch['week']} findes ikke i {ch['programId']}")
    for k in ("ctlTarget", "tssTarget"):
        v = ch.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            wk[k] = int(round(v))
    return wk


def target_changes_for_data(plan: dict, changes: list) -> list:
    """[{programId, week, isoWeek, start, ctlBefore, ctlAfter, tssBefore, tssAfter}]
    for hver set_week_targets — til forslagskortet."""
    out = []
    for ch in changes:
        if ch.get("action") != "set_week_targets":
            continue
        prog = (plan.get("programs") or {}).get(ch["programId"]) or {}
        wk = next((w for w in (prog.get("weeks") or []) if w.get("week") == ch["week"]), {})
        start = wk.get("start")
        out.append({
            "programId": ch["programId"], "week": ch["week"],
            "isoWeek": date.fromisoformat(start).isocalendar()[1] if start else None,
            "start": start, "blockType": wk.get("blockType"),
            "ctlBefore": wk.get("ctlTarget"), "ctlAfter": ch.get("ctlTarget", wk.get("ctlTarget")),
            "tssBefore": wk.get("tssTarget"), "tssAfter": ch.get("tssTarget", wk.get("tssTarget")),
        })
    return out


# -- kælderkvoter pr. berørt uge ----------------------------------------------

def _week_key(plan: dict, d_iso: str, athlete: str):
    prog = _programs.active_program(plan, athlete, today=d_iso)
    if not prog:
        return None
    w = _programs.week_no_raw(prog, d_iso)
    return (prog.get("id") or prog.get("name"), w, _programs.week_start(prog, w).isoformat())


def week_library_ids(plan: dict, athlete: str, week_start_iso: str) -> list:
    """libraryId'er (kun kendte kælderpas) i ugen der starter mandag `week_start_iso`."""
    start = date.fromisoformat(week_start_iso)
    known = set(bike_library.ids())
    out = []
    for d in plan["athletes"][athlete]["days"]:
        dd = date.fromisoformat(d["date"])
        if 0 <= (dd - start).days < 7:
            for e in d.get("entries") or []:
                lid = e.get("libraryId")
                if lid in known and e.get("workout"):
                    out.append(lid)
    return out


def check_weeks(plan: dict, dates: list, athlete: str = "kennet") -> list:
    """bike_library.check_week() for hver programuge de ændrede datoer rammer.
    Returnerer [(ugelabel, [advarsler])] — kun uger med brud."""
    weeks = {}
    for d_iso in dates:
        k = _week_key(plan, d_iso, athlete)
        if k:
            weeks[k] = True
    out = []
    for (_pid, w, ws) in sorted(weeks, key=lambda k: k[2]):
        warn = bike_library.check_week(week_library_ids(plan, athlete, ws))
        if warn:
            out.append((f"uge {w} ({ws})", warn))
    return out


def week_load_counts(plan: dict, athlete: str, week_start_iso: str) -> dict:
    """{haard, moderat, let} for ugen — til rapport/kvote-sammenligning."""
    counts = {"haard": 0, "moderat": 0, "let": 0}
    for lid in week_library_ids(plan, athlete, week_start_iso):
        counts[bike_library.load_of(lid)] = counts.get(bike_library.load_of(lid), 0) + 1
    return counts


# -- data.json-visning --------------------------------------------------------

def _names(entries) -> list:
    out = []
    for e in entries or []:
        wo = e.get("workout")
        if wo and wo.get("name"):
            out.append(wo["name"] + (" (valgfri)" if e.get("optional") else ""))
    return out


def summarize_for_data(plan: dict, prop: dict, athlete: str = "kennet") -> dict:
    """Ét element til data.json's `proposals`: before = nuværende plan,
    after = forslaget, grupperet pr. ISO-uge (mandag start)."""
    days = {d["date"]: d for d in plan["athletes"][athlete]["days"]}
    sim, dates = apply_changes(plan, prop["changes"], athlete)
    sim_days = {d["date"]: d for d in sim["athletes"][athlete]["days"]}
    weeks = {}
    for d_iso in sorted(dates):
        dd = date.fromisoformat(d_iso)
        iso_week = dd.isocalendar()[1]
        start = date.fromordinal(dd.toordinal() - dd.weekday()).isoformat()
        wk = weeks.setdefault(start, {"isoWeek": iso_week, "start": start, "days": []})
        wk["days"].append({
            "date": d_iso,
            "before": _names((days.get(d_iso) or {}).get("entries")),
            "after": _names((sim_days.get(d_iso) or {}).get("entries")),
        })
    return {
        "id": prop["id"],
        "title": prop.get("title", ""),
        "createdAt": prop.get("createdAt"),
        "status": prop.get("status"),
        "summary": list(prop.get("summary") or []),
        "note": prop.get("note") or "",
        "weeks": [weeks[k] for k in sorted(weeks)],
        "targets": target_changes_for_data(plan, prop["changes"]),
    }


def build_data_proposals(plan: dict, root: Optional[Path] = None,
                         athlete: str = "kennet") -> list:
    """data.json['proposals'] — alle pending forslag; tomt array når ingen."""
    out = []
    for prop in list_pending(root):
        try:
            out.append(summarize_for_data(plan, prop, athlete))
        except Exception as e:                       # ét defekt forslag må ikke vælte resten
            print(f"  forslag {prop.get('id')}: kunne ikke opsummeres ({e})")
    return out


# -- beslutning ---------------------------------------------------------------

def decide(prop: dict, status: str, result: Optional[dict] = None,
           now: Optional[datetime] = None) -> dict:
    """Sætter status/decidedAt/result (kopi)."""
    if status not in STATUSES or status == "pending":
        raise ValueError(f"Ugyldig beslutning {status!r}")
    out = dict(prop)
    out["status"] = status
    out["decidedAt"] = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    out["result"] = result
    return out


# -- offline anvendelse (samme kode som live) ---------------------------------

def apply_offline(pid: str, plan_path: Optional[Path] = None,
                  root: Optional[Path] = None, confirmed_warn: bool = False,
                  write: bool = True) -> dict:
    """Anvender forslaget på data/plan.json gennem edit_apply.apply_edit
    (action 'apply_proposal') — NØJAGTIG samme vej som plan-edit.yml, blot
    uden Intervals/Outlook/GitHub. Sætter status 'applied-offline'."""
    from . import edit_apply
    plan_path = plan_path or (ROOT / "data" / "plan.json")
    prop = load(pid, root)
    plan_raw = plan_path.read_text(encoding="utf-8")
    res = edit_apply.apply_edit(plan_raw, "apply_proposal", ENTRY_ID_PREFIX + pid,
                                {"proposal": prop}, confirmed_warn=confirmed_warn)
    if res["status"] != "ok":
        return res
    if write:
        plan_path.write_text(res["new_plan_raw"], encoding="utf-8")
        save(decide(prop, "applied-offline",
                    {"dates_changed": res["dates_changed"], "commit": None}), root)
    return res


def _cli(argv):
    import sys
    if len(argv) >= 2 and argv[0] == "apply-offline":
        res = apply_offline(argv[1], confirmed_warn="--confirm-warn" in argv,
                            write="--dry-run" not in argv)
        print(f"{res['status']}: {res['gate']['msg']}")
        print(f"datoer: {len(res['dates_changed'])} — {', '.join(res['dates_changed'])}")
        return 0 if res["status"] == "ok" else 1
    print("brug: python3 -m modules.proposals apply-offline <id> [--confirm-warn] [--dry-run]",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
