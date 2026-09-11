# -*- coding: utf-8 -*-
"""
Entry point kaldt af .github/workflows/plan-edit.yml

Læser client_payload fra GH event, orkestrerer:
  1. Load plan.json
  2. Kør edit_apply.apply_edit (Friel-gate + simulation)
  3. Ved OK: commit plan.json, opdatér Intervals+Outlook for berørte datoer,
     generér Word-masters, skriv edit_result.json
  4. Ved WARN/REJECT: skriv kun edit_result.json (klienten viser til bruger)

Fejl i Intervals/Outlook standser IKKE plan.json-commit (sandheden er sikret),
men rapporteres i edit_result.json — næste scheduled sync fanger rest.
"""
import base64
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modules import edit_apply, martin_signals, outlook_times, proposals, word_master


GH_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
API_KEY = os.environ["INTERVALS_API_KEY"]
ATHLETE_ID = os.environ.get("INTERVALS_ATHLETE_ID") or "i599466"
AZURE_TENANT = os.environ.get("AZURE_TENANT_ID")
AZURE_CLIENT = os.environ.get("AZURE_CLIENT_ID")
AZURE_SECRET = os.environ.get("AZURE_CLIENT_SECRET")
OUTLOOK_USER = "kennet@hammerby.com"

GH = f"https://api.github.com/repos/{REPO}/contents"
GH_HEADERS = {"Authorization": f"Bearer {GH_TOKEN}",
              "Accept": "application/vnd.github+json"}
INTERVALS = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
INTERVALS_AUTH = ("API_KEY", API_KEY)


# -- GitHub Contents API --------------------------------------------------

def gh_get(path, ref=None):
    url = f"{GH}/{path}"
    if ref: url += f"?ref={ref}"
    r = requests.get(url, headers=GH_HEADERS, timeout=30)
    if r.status_code == 200:
        d = r.json()
        return d["sha"], base64.b64decode(d["content"]).decode("utf-8") if d.get("content") else None
    if r.status_code == 404:
        return None, None
    r.raise_for_status()


def gh_get_bytes(path):
    r = requests.get(f"{GH}/{path}", headers=GH_HEADERS, timeout=30)
    if r.status_code == 200:
        d = r.json()
        return d["sha"], base64.b64decode(d["content"]) if d.get("content") else b""
    if r.status_code == 404:
        return None, b""
    r.raise_for_status()


def gh_put(path, sha, content_bytes, message):
    body = {"message": message, "content": base64.b64encode(content_bytes).decode()}
    if sha:
        body["sha"] = sha
    r = requests.put(f"{GH}/{path}", headers={**GH_HEADERS, "Content-Type": "application/json"},
                     json=body, timeout=45)
    r.raise_for_status()
    return r.json()["commit"]["sha"]


# -- Intervals ------------------------------------------------------------

def intervals_delete_date(day_iso: str) -> int:
    r = requests.get(f"{INTERVALS}/events", auth=INTERVALS_AUTH,
                     params={"oldest": day_iso, "newest": day_iso},
                     timeout=30)
    r.raise_for_status()
    events = [e for e in r.json() if e.get("category") == "WORKOUT"]
    n = 0
    for e in events:
        d = requests.delete(f"{INTERVALS}/events/{e['id']}",
                            auth=INTERVALS_AUTH, timeout=30)
        if d.status_code in (200, 204, 404):
            n += 1
    return n


def intervals_create(day_iso: str, workout: dict):
    payload = {
        "start_date_local": f"{day_iso}T06:00:00",
        "category": "WORKOUT",
        "type": workout.get("type") or "Workout",
        "name": workout["name"],
        "moving_time": workout.get("moving_time", 0),
        "description": workout.get("description", ""),
    }
    r = requests.post(f"{INTERVALS}/events", auth=INTERVALS_AUTH,
                      json=payload, timeout=30)
    r.raise_for_status()
    return r.json().get("id")


# -- Outlook (Graph) ------------------------------------------------------

def _is_iso_date(value) -> bool:
    """True for 'YYYY-MM-DD' — alt andet (fx 'restore') er ikke en synk-dato."""
    try:
        date.fromisoformat(str(value))
        return True
    except (TypeError, ValueError):
        return False


def outlook_token():
    r = requests.post(
        f"https://login.microsoftonline.com/{AZURE_TENANT}/oauth2/v2.0/token",
        data={"grant_type": "client_credentials",
              "client_id": AZURE_CLIENT, "client_secret": AZURE_SECRET,
              "scope": "https://graph.microsoft.com/.default"},
        timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def outlook_sync_date(day_iso: str, entries: list, token: str, overrides: dict = None):
    """Slet dagens Træning-events og genskab dem fra plan.json-entries.
    overrides: normaliserede timeOverrides ({dato: (h, m) | {disciplin: (h, m)}})."""
    graph = f"https://graph.microsoft.com/v1.0/users/{OUTLOOK_USER}"
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params = {"startDateTime": f"{day_iso}T00:00:00",
              "endDateTime": f"{day_iso}T23:59:59",
              "$select": "id,subject,categories", "$top": "50"}
    r = requests.get(f"{graph}/calendarView", headers=hdrs, params=params, timeout=30)
    r.raise_for_status()
    for ev in r.json().get("value", []):
        cats = ev.get("categories", [])
        if any(c in ("Træning", "Traening") for c in cats):
            requests.delete(f"{graph}/events/{ev['id']}", headers=hdrs, timeout=30)

    # Tider fra modules/outlook_times.py (blok 8) — SAMME regel som ugesynken
    # (sync_outlook.py): styrke 06:30 først, +15 min mellem pas, aldrig overlap,
    # timeOverrides pr. pas. Før havde denne funktion sin egen tidstabel.
    workouts = outlook_times.workouts_from_entries(day_iso, entries)
    for wo, start_dt in outlook_times.schedule_day(workouts, (overrides or {}).get(day_iso)):
        requests.post(f"{graph}/events", headers=hdrs,
                      json=outlook_times.event_body(wo, start_dt), timeout=30)


# -- Forslag (blok 9) -----------------------------------------------------

def proposal_decide(pid: str, status: str, result: dict, inline: dict = None) -> str:
    """Sæt status/decidedAt/result i data/proposals/<pid>.json på GitHub.
    Læser den friske fil (ikke checkout'et) så en samtidig ændring ikke
    overskrives. Findes filen ikke, men forslaget kom inline i payload'en
    (Cowork-vejen 11/9-2026: Claude sender hele forslaget via Worker'en),
    oprettes filen nu — så historikken i data/proposals er komplet."""
    rel = f"data/proposals/{pid}.json"
    sha, raw = gh_get(rel)
    if raw is None:
        if not inline:
            raise ValueError(f"{rel} findes ikke i repoet")
        sha, prop_src = None, inline
    else:
        prop_src = json.loads(raw)
    prop = proposals.decide(prop_src, status, result)
    return gh_put(rel, sha, proposals.dumps(prop).encode(),
                  f"forslag {pid}: {status}")


# -- Main -----------------------------------------------------------------

def write_result(request_id: str, payload: dict):
    """Skriv edit_result.json så klienten kan polle. Struktur: dict {requestId: {...}}."""
    sha, raw = gh_get("data/edit_result.json")
    results = json.loads(raw) if raw else {}
    # Rul historik: behold sidste 10 requests
    payload["request_id"] = request_id
    results[request_id] = payload
    if len(results) > 10:
        # Slet ældste
        sorted_ids = sorted(results.items(), key=lambda kv: kv[1].get("request_ts", ""))
        for k, _ in sorted_ids[:-10]:
            del results[k]
    gh_put("data/edit_result.json", sha,
           (json.dumps(results, ensure_ascii=False, indent=1) + "\n").encode(),
           f"edit_result: {request_id[:12]} {payload.get('status')}")


def main():
    event = json.loads(os.environ["GH_EVENT_PAYLOAD"])
    cp = event.get("client_payload", {})
    request_id = cp.get("requestId") or datetime.now(timezone.utc).strftime("r%Y%m%dT%H%M%SZ")
    action = cp["action"]
    entry_id = cp["entryId"]
    params = cp.get("params") or {}
    confirmed_warn = bool(cp.get("confirmedWarn"))
    athlete = cp.get("athlete", "kennet")  # default kennet for bagudkompatibilitet

    print(f"=== plan-edit request {request_id}: {action} on {entry_id} (athlete={athlete}) ===")
    print(f"params: {json.dumps(params, ensure_ascii=False)[:200]}")

    _plan_sha, plan_raw = gh_get("data/plan.json")

    # Special: restore_from_commit — hent den gamle plan fra source_commit
    if action == "restore_from_commit" and params.get("source_commit") and not params.get("restored_plan"):
        try:
            _, old_raw = gh_get("data/plan.json", ref=params["source_commit"])
            params = dict(params, restored_plan=json.loads(old_raw))
            print(f"Restore: hentede plan fra commit {params['source_commit'][:7]}")
        except Exception as e:
            write_result(request_id, {
                "status": "reject",
                "gate": {"msg": f"Kunne ikke hente plan fra commit: {e}"},
                "request_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            return

    # Special dry-run action: bare returnér alternativer, commit intet
    if action == "suggest_move":
        result = edit_apply.suggest_move_alternatives(
            plan_raw, entry_id, athlete=athlete,
            window_days=int(params.get("window_days", 7)))
        write_result(request_id, {
            "status": "suggestion",
            "action": "suggest_move",
            "athlete": athlete,
            "src_date": result.get("src_date"),
            "alternatives": result.get("alternatives", []),
            "error": result.get("error"),
            "request_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        print(f"Suggest-move: {len(result.get('alternatives', []))} alternativer")
        return

    result = edit_apply.apply_edit(plan_raw, action, entry_id, params,
                                    confirmed_warn=confirmed_warn, athlete=athlete)

    # Forslag (blok 9): reject_proposal ændrer ikke planen — kun forslagsfilen.
    if action == "reject_proposal" and result["status"] == "ok":
        pid = result["proposal_id"]
        try:
            _pcommit = proposal_decide(pid, "rejected",
                                       {"reason": params.get("reason") or None})
        except Exception as ex:
            write_result(request_id, {
                "status": "reject", "action": action, "proposal_id": pid,
                "gate": {"msg": f"Kunne ikke opdatere forslagsfilen: {ex}"},
                "dates_changed": [], "athlete": athlete, "request_ts": result["request_ts"],
            })
            return
        write_result(request_id, {
            "status": "ok", "action": action, "proposal_id": pid,
            "gate": result["gate"], "dates_changed": [], "plan_commit": None,
            "proposal_commit": _pcommit, "sync_errors": [],
            "athlete": athlete, "request_ts": result["request_ts"],
        })
        print(f"=== FÆRDIG: forslag {pid} afvist ===")
        return

    if result["status"] != "ok":
        print(f"Gate returnerede {result['status']}: {result['gate']['msg']}")
        write_result(request_id, {
            "status": result["status"], "gate": result["gate"],
            "dates_changed": result["dates_changed"],
            "athlete": athlete,
            "request_ts": result["request_ts"],
        })
        return

    # COMMIT plan.json — sandheden først
    plan_sha_fresh, _ = gh_get("data/plan.json")  # frisk SHA
    _what = entry_id if action in ("strength_log", "strength_checkin", "apply_proposal") else entry_id[:8]
    _dates_msg = (f"{len(result['dates_changed'])} datoer" if len(result["dates_changed"]) > 14
                  else ", ".join(result["dates_changed"]))
    plan_commit = gh_put("data/plan.json", plan_sha_fresh,
                          result["new_plan_raw"].encode(),
                          f"plan-edit: {athlete} {action} {_what} ({_dates_msg})")
    print(f"plan.json commit: {plan_commit[:7]}")

    # Forslag (blok 9): markér accepteret lige efter plan-commit'et, så
    # data.json's forslag-kort forsvinder ved næste pipeline-kørsel selv om
    # Intervals/Outlook skulle fejle nedenfor. Fejl her er ikke-fatale.
    proposal_id = result.get("proposal_id")
    proposal_commit = None
    _proposal_error = None
    if action == "apply_proposal":
        try:
            proposal_commit = proposal_decide(
                proposal_id, "accepted",
                {"dates_changed": result["dates_changed"], "commit": plan_commit},
                inline=params.get("proposal"))
            print(f"forslag {proposal_id} accepteret: {proposal_commit[:7]}")
        except Exception as ex:
            _proposal_error = f"Forslag {proposal_id}: {ex}"
            print(f"FEJL forslagsfil: {ex}")

    # Styrke-log (blok 8) og check-in (blok 10): kun plan.json + edit_result. Intet pas er ændret,
    # så Intervals/Outlook/Martin-signal/Word/OneDrive springes over.
    if action in ("strength_log", "strength_checkin"):
        write_result(request_id, {
            "status": "ok",
            "action": action,
            "gate": result["gate"],
            "dates_changed": [],
            "plan_commit": plan_commit,
            "sync_errors": [],
            "athlete": athlete,
            "request_ts": result["request_ts"],
        })
        print(f"=== FÆRDIG: {'check-in' if action == 'strength_checkin' else 'styrkelog'} {entry_id} gemt ===")
        return

    dates = result["dates_changed"]
    new_plan = json.loads(result["new_plan_raw"])
    days_map = {d["date"]: d for d in new_plan["athletes"][athlete]["days"]}
    sync_errors = [_proposal_error] if _proposal_error else []

    # Martin-signal (T5): kostrelevante ændringer -> data/martin_signals.md.
    # Non-fatal — må aldrig stoppe edit-flowet, fejl logges kun til stdout.
    try:
        signal = martin_signals.build_signal(
            json.loads(plan_raw), new_plan, action, dates, athlete=athlete)
        if signal:
            ms_sha, ms_raw = gh_get("data/martin_signals.md")
            gh_put("data/martin_signals.md", ms_sha,
                   martin_signals.append_signal(ms_raw or "", signal).encode(),
                   f"martin-signal: {action} ({', '.join(dates)})")
            print("Martin-signal skrevet til data/martin_signals.md")
        else:
            print("Martin-signal: ændring ikke kostrelevant — intet logget")
    except Exception as ex:
        print(f"ADVARSEL Martin-signal fejlede (ignoreres): {ex}")

    # dates_changed kan indeholde ikke-datoer — restore_from_commit giver
    # ["restore"] (hele planen), og der findes ingen dato at synke. Sådanne
    # værdier springes over i Intervals/Outlook i stedet for at blive sendt
    # som dato (3/9-2026: "restore" blev sendt til Outlook som en dato).
    sync_dates = [d for d in dates if _is_iso_date(d)]
    skipped = [d for d in dates if not _is_iso_date(d)]
    if skipped:
        print(f"Intervals/Outlook: springer ikke-datoer over: {', '.join(skipped)}")

    # Intervals+Outlook: KUN for Kennet — Eva bruger .ics-eksport i stedet.
    # Et forslag (apply_proposal) kan ramme mange datoer (uge 3-8 = 40+);
    # de synkes ALLE gennem samme per-dato-løkke, med ét Outlook-token.
    if len(sync_dates) > 14:
        print(f"Batch-synk: {len(sync_dates)} datoer")
    if athlete == "kennet":
        # Intervals — for hver berørt dato: slet+opret
        for d_iso in sync_dates:
            try:
                n = intervals_delete_date(d_iso)
                print(f"Intervals slettet {d_iso}: {n} events")
                day = days_map.get(d_iso, {"entries": []})
                for e in day.get("entries", []):
                    wo = e.get("workout")
                    if wo:
                        intervals_create(d_iso, wo)
                        print(f"  Intervals oprettet: {wo['name']}")
            except Exception as ex:
                sync_errors.append(f"Intervals {d_iso}: {ex}")
                print(f"FEJL Intervals {d_iso}: {ex}")
    else:
        print(f"Springer Intervals+Outlook over for {athlete} — hun bruger .ics-eksport")

    # Outlook — kun for Kennet
    if athlete == "kennet":
        try:
            tok = outlook_token()
            _overrides = outlook_times.normalize_overrides(
                new_plan["athletes"][athlete].get("timeOverrides"))
            for d_iso in sync_dates:
                try:
                    day = days_map.get(d_iso, {"entries": []})
                    outlook_sync_date(d_iso, day.get("entries", []), tok, _overrides)
                    print(f"Outlook synk: {d_iso}")
                except Exception as ex:
                    sync_errors.append(f"Outlook {d_iso}: {ex}")
                    print(f"FEJL Outlook {d_iso}: {ex}")
        except Exception as ex:
            sync_errors.append(f"Outlook token: {ex}")
            print(f"FEJL Outlook token: {ex}")

    # Word-masters — genereres altid ved plan-ændring
    try:
        docs = word_master.generate_both(new_plan)
        for path, blob in docs.items():
            sha, _ = gh_get_bytes(path)
            gh_put(path, sha, blob, f"masterplan opdateret ({action} {entry_id[:8]})")
            Path(path).write_bytes(blob)  # lokal kopi -> OneDrive-sync nedenfor
            print(f"Word skrevet: {path}")
    except Exception as ex:
        sync_errors.append(f"Word: {ex}")
        print(f"FEJL Word: {ex}")

    # OneDrive-sync kaldes EKSPLICIT. Push-trigger paa sync-onedrive.yml virker
    # ikke: gh_put() bruger GITHUB_TOKEN, og GitHub udloeser aldrig workflows fra
    # GITHUB_TOKEN-commits. Verificeret 16/7-2026 (plan-edit koerte 2x 13/7,
    # sync-onedrive fyrede aldrig).
    try:
        import subprocess
        root = Path(__file__).resolve().parent.parent
        subprocess.run([sys.executable, str(root / "scripts" / "sync_to_onedrive.py")],
                       check=True, cwd=str(root))
        print("OneDrive sync OK")
    except Exception as ex:
        sync_errors.append(f"OneDrive: {ex}")
        print(f"FEJL OneDrive: {ex}")

    payload = {
        "status": "ok",
        "gate": result["gate"],
        "dates_changed": dates,
        "plan_commit": plan_commit,
        "sync_errors": sync_errors,
        "athlete": athlete,
        "request_ts": result["request_ts"],
    }
    if proposal_id:
        payload.update({"action": action, "proposal_id": proposal_id,
                        "proposal_commit": proposal_commit})
    write_result(request_id, payload)
    print(f"=== FÆRDIG: {len(sync_errors)} sync-fejl ===")


if __name__ == "__main__":
    main()
