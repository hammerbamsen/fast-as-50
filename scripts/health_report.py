# -*- coding: utf-8 -*-
"""
Workflow-sundhed → health.json (blok 7, 7/9-2026).

Kaldes af .github/workflows/health.yml efter HVER afsluttet kørsel af de
øvrige workflows (on: workflow_run, types: [completed]) og ved manuel start.

Flow:
  1. Læs health.json fra repo-roden via Contents API (modules/github.gh_get —
     retry + timeout). Findes den ikke: start fra en tom struktur.
  2. merge_run(): opdatér workflows[<navn>] med lastRun, conclusion, event,
     runUrl, durationS og expectedEveryMin (fast tabel nedenfor). Sæt
     secrets.PRIVATE_REPO_TOKEN (udløb 15/10-2026) og generatedAt.
  3. Skriv tilbage via gh_put med commit-besked "health: <workflow> <conclusion>".
  4. Var kørslen ikke success: send én push-alert til Kennet via
     send_push.main(["--alert", ...]). Fejler pushen, er det IKKE en fejl her.

Exit 0 selv hvis pushen fejler. Exit 1 KUN hvis health.json ikke kunne skrives.

Miljø (sat af health.yml):
  RUN_NAME, RUN_CONCLUSION, RUN_EVENT, RUN_URL, RUN_STARTED_AT, RUN_UPDATED_AT
      — fra github.event.workflow_run (tomme ved workflow_dispatch → kun
        generatedAt/secrets opdateres)
  GH_TOKEN            — GITHUB_TOKEN (contents: write) til health.json
  PRIVATE_REPO, PRIVATE_REPO_TOKEN, VAPID_PRIVATE, VAPID_SUBJECT, GITHUB_TOKEN,
  GITHUB_REPOSITORY   — videre til send_push.py (kun brugt ved alert)

Kontrakten for health.json (læses af dashboardets System-kort med
cache:'no-store') står i docs/PIPELINE.md. Dashboardet regner selv alder og
farver — filen indeholder ingen anden tilstand.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

HEALTH_PATH = "health.json"

# Hvor ofte et workflow forventes at køre (minutter). Dashboardet farver GULT
# når lastRun er ældre end 2× dette. Workflows uden forventning (manuelle
# værktøjer, event-drevne) står ikke her og får ingen expectedEveryMin.
WEEK_MIN = 7 * 24 * 60
EXPECTED_EVERY_MIN = {
    "Daglig dashboard-opdatering": 60,          # */30-cron, i praksis 1-2 t
    "Send daglig push-påmindelse": 1500,        # 05:00 + 17:00 UTC → ~25 t = tolerance
    "Byg workouts i Intervals.icu": WEEK_MIN,   # søndag 05:00 UTC
    "Sync workouts til Outlook kalender": WEEK_MIN,  # søndag 18:00 UTC (+ efter build)
}

# Nøgler til det private repo (push-subscriptions). To tilstande:
#   pat  — fine-grained PAT i secrets.PRIVATE_REPO_TOKEN, udløber 15/10-2026.
#   app  — installations-token mintet pr. kørsel af actions/create-github-app-token
#          fra den GitHub App Worker'en allerede bruger. Udløber aldrig.
# Workflowet sætter PRIVATE_REPO_AUTH; dashboardet viser nedtælling for pat
# (grøn > 21 d, gul ≤ 21 d, rød ≤ 7 d/udløbet) og "udløber ikke" for app.
# Opsætning: docs/PAT_RENEWAL.md.
PRIVATE_REPO_USED_BY = ["Send daglig push-påmindelse", "Modtag push-subscription",
                        "Workflow-sundhed"]
PAT_EXPIRES = "2026-10-15"


def secrets_for(auth_mode):
    """health.json's secrets-blok ud fra hvordan det private repo autentificeres.
    Ukendt/tom værdi behandles som 'pat' — den sikre antagelse, for så bliver
    udløbet ved med at være synligt i stedet for at forsvinde tavst."""
    if str(auth_mode or "").strip().lower() == "app":
        return {
            "GitHub App (privat repo)": {
                "usedBy": list(PRIVATE_REPO_USED_BY),
                "note": "Installations-token mintes pr. kørsel — udløber ikke. "
                        "App 4259031, samme som Cloudflare Worker'en.",
            },
        }
    return {
        "PRIVATE_REPO_TOKEN": {
            "expires": PAT_EXPIRES,
            "usedBy": list(PRIVATE_REPO_USED_BY),
            "note": "Fine-grained PAT til det private repo (push-subscriptions). "
                    "Erstattes af GitHub App-token — se docs/PAT_RENEWAL.md.",
        },
    }


# "cancelled" er næsten altid GitHubs concurrency-kø (en nyere kørsel afløser en
# ventende) eller et bevidst stop — ingen af delene fortjener en push-alarm (10/9).
ALERT_CONCLUSIONS_IGNORED = ("success", "skipped", "cancelled")


# ── Ren logik (testes i scripts/test_health_report.py) ──────────────────────

def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s):
    """GitHub-tidsstempel ('2026-09-07T04:31:12Z') → aware datetime, ellers None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def duration_s(run):
    a, b = parse_ts(run.get("run_started_at")), parse_ts(run.get("updated_at"))
    if not a or not b:
        return None
    return max(0, int(round((b - a).total_seconds())))


def empty_health():
    return {"generatedAt": None, "workflows": {}, "secrets": {}}


def merge_run(health, run, now, auth_mode=None):
    """Returnerer en NY health-dict med kørslen `run` indarbejdet.

    `run` = {name, conclusion, event, html_url, run_started_at, updated_at}
    (feltnavne som github.event.workflow_run). `run` må være None/tom ved
    manuel start — så opdateres kun generatedAt og secrets.

    `auth_mode` = env PRIVATE_REPO_AUTH ('app' eller 'pat', se secrets_for).
    """
    out = json.loads(json.dumps(health)) if health else empty_health()
    out.setdefault("workflows", {})
    out.setdefault("secrets", {})

    name = (run or {}).get("name")
    if name:
        entry = dict(out["workflows"].get(name) or {})
        entry["lastRun"] = run.get("updated_at") or _iso(now)
        entry["conclusion"] = run.get("conclusion") or "unknown"
        entry["event"] = run.get("event") or ""
        entry["runUrl"] = run.get("html_url") or ""
        entry["durationS"] = duration_s(run)
        if name in EXPECTED_EVERY_MIN:
            entry["expectedEveryMin"] = EXPECTED_EVERY_MIN[name]
        else:
            entry.pop("expectedEveryMin", None)
        out["workflows"][name] = entry

    out["secrets"] = secrets_for(auth_mode)
    out["generatedAt"] = _iso(now)
    return out


def needs_alert(run):
    return bool(run and run.get("name")) and \
        (run.get("conclusion") or "unknown") not in ALERT_CONCLUSIONS_IGNORED


def alert_text(run, now):
    """(titel, brødtekst) til push-alerten. Tidspunkt i dansk lokaltid."""
    try:
        from zoneinfo import ZoneInfo
        local = (parse_ts(run.get("updated_at")) or now).astimezone(ZoneInfo("Europe/Copenhagen"))
    except Exception:  # zoneinfo/tzdata mangler — fald tilbage til UTC
        local = parse_ts(run.get("updated_at")) or now
    title = f"Workflow fejlede: {run.get('name')}"
    body = f"{run.get('conclusion') or 'unknown'} · {local.strftime('%d/%m %H:%M')} · tryk for at se System-kortet"
    return title, body


def run_from_env(env=None):
    env = os.environ if env is None else env
    if not env.get("RUN_NAME"):
        return None
    return {
        "name": env.get("RUN_NAME"),
        "conclusion": env.get("RUN_CONCLUSION") or "unknown",
        "event": env.get("RUN_EVENT") or "",
        "html_url": env.get("RUN_URL") or "",
        "run_started_at": env.get("RUN_STARTED_AT") or "",
        "updated_at": env.get("RUN_UPDATED_AT") or "",
    }


# ── I/O ─────────────────────────────────────────────────────────────────────

def _load_health(github):
    sha, raw = github.gh_get(HEALTH_PATH)
    if raw is None:
        print("  health.json findes ikke — starter fra tom struktur")
        return None, empty_health()
    try:
        return sha, json.loads(raw)
    except ValueError as e:
        print(f"  health.json er ugyldig JSON ({e}) — starter forfra")
        return sha, empty_health()


def _write_health(github, sha, health, message):
    content = json.dumps(health, ensure_ascii=False, indent=2) + "\n"
    if sha:
        return github.gh_put(HEALTH_PATH, sha, content, message)
    # Første skrivning: Contents API vil ikke have et sha-felt ved oprettelse.
    # Genbruger github._request (retry/backoff) frem for at duplikere PUT-logikken.
    import base64
    body = {"message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode()}
    r = github._request("PUT", f"https://api.github.com/repos/{github.REPO}/contents/{HEALTH_PATH}", json=body)
    ok = r is not None and r.status_code in (200, 201)
    print(f"  {'✅' if ok else '❌'} {HEALTH_PATH} oprettet: {r.status_code if r is not None else 'ingen svar'}")
    return ok


def _send_alert(run, now):
    """Push via send_push.main(--alert). Aldrig blokerende."""
    title, body = alert_text(run, now)
    url = os.environ.get("ALERT_URL", "./#more")
    try:
        import send_push
        rc = send_push.main(["--alert", title, body, "--url", url])
        print(f"  alert-push: send_push exit {rc}")
    except Exception as e:  # noqa: BLE001 — pushen må aldrig vælte health-skrivningen
        print(f"  alert-push fejlede (ikke-blokerende): {type(e).__name__}: {e}")


def main():
    from modules import github
    now = datetime.now(timezone.utc)
    run = run_from_env()
    if run:
        print(f"Kørsel: {run['name']} → {run['conclusion']} ({run['event']})")
    else:
        print("Ingen workflow_run i miljøet (manuel start) — opdaterer kun generatedAt/secrets")

    sha, health = _load_health(github)
    auth_mode = os.environ.get("PRIVATE_REPO_AUTH", "")
    merged = merge_run(health, run, now, auth_mode)
    print(f"Privat repo-auth: {auth_mode or 'pat (antaget)'}")
    message = f"health: {run['name']} {run['conclusion']}" if run else "health: manuel opdatering"
    ok = _write_health(github, sha, merged, message)

    if needs_alert(run):
        _send_alert(run, now)

    if not ok:
        print("❌ health.json kunne ikke skrives")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
