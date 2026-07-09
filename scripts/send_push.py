# -*- coding: utf-8 -*-
"""
U2 — send daglig push-påmindelse. Kaldes af .github/workflows/send-push.yml (cron).

Flow:
  1. Hent plan.json fra dette (offentlige) repo.
  2. Hent push_subscriptions.json fra det PRIVATE repo (PRIVATE_REPO / PRIVATE_REPO_TOKEN).
  3. For hver atlet: byg dagens besked (modules.push_send). Hviledag => spring over.
  4. Send til hver af atletens subscriptions via pywebpush + VAPID.
  5. Fjern døde subscriptions (404/410) og skriv listen tilbage til det private repo.

Miljø (Actions secrets):
  GITHUB_TOKEN          - indbygget, læser plan.json i dette repo
  GITHUB_REPOSITORY     - indbygget, "hammerbamsen/fast-as-50"
  PRIVATE_REPO          - fx "hammerbamsen/fast-as-50-private"
  PRIVATE_REPO_TOKEN    - fine-grained PAT med contents:rw på PRIVATE_REPO
  VAPID_PRIVATE         - VAPID privatnøgle (base64url raw scalar)
  VAPID_SUBJECT         - "mailto:kennet@hammerby.com"

Idempotent og ikke-blokerende: fejl mod én subscription stopper ikke de andre.
"""
import base64
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modules import push_send

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None
    WebPushException = Exception


GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "hammerbamsen/fast-as-50")
PRIVATE_REPO = os.environ.get("PRIVATE_REPO", "")
PRIVATE_TOKEN = os.environ.get("PRIVATE_REPO_TOKEN", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:kennet@hammerby.com")

SUBS_PATH = "push_subscriptions.json"
ATHLETES = ("kennet", "eva")

# Aften-påmindelse (PUSH_MODE=evening): fast AF-check-in-nudge, kun til Kennet.
AF_EVENING_MSG = {
    "title": "Aften-check-in \U0001F4AA",
    "body": "Husk dagens AF-check-in",
    "tag": "fast50-af-evening",   # eget tag => kolliderer ikke med daglig push
    "url": "af.html",
    "athlete": "kennet",
}


def _gh_get_raw(repo, path, token):
    """Returnerer (sha, tekst) eller (None, None)."""
    r = requests.get(f"https://api.github.com/repos/{repo}/contents/{path}",
                     headers={"Authorization": f"Bearer {token}",
                              "Accept": "application/vnd.github+json"}, timeout=30)
    if r.status_code == 200:
        d = r.json()
        return d["sha"], base64.b64decode(d["content"]).decode("utf-8")
    if r.status_code == 404:
        return None, None
    r.raise_for_status()


def _gh_put(repo, path, sha, content, message, token):
    body = {"message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode(),
            **({"sha": sha} if sha else {})}
    r = requests.put(f"https://api.github.com/repos/{repo}/contents/{path}",
                     headers={"Authorization": f"Bearer {token}",
                              "Accept": "application/vnd.github+json"},
                     json=body, timeout=30)
    ok = r.status_code in (200, 201)
    print(f"  {'OK' if ok else 'FEJL'} skriv {repo}/{path}: {r.status_code}")
    return ok


def _load_subscriptions():
    if not (PRIVATE_REPO and PRIVATE_TOKEN):
        print("  Intet privat repo/token konfigureret — springer over.")
        return None, []
    sha, raw = _gh_get_raw(PRIVATE_REPO, SUBS_PATH, PRIVATE_TOKEN)
    if raw is None:
        return None, []
    try:
        return sha, json.loads(raw).get("subscriptions", [])
    except (ValueError, AttributeError):
        return sha, []


def run_send(plan, subs, today, sender):
    """
    Ren send-orkestrering — INGEN netværk/env. `sender(sub, payload)` udfører
    selve afsendelsen og returnerer:
      - True  ved succes
      - int (HTTP-status) ved fejl (404/410 => død subscription fjernes)
      - False ved anden ikke-blokerende fejl
    Returnerer (sent, dead_endpoints, pruned_subs_or_None).
    """
    dead = set()
    sent = 0
    for athlete in ATHLETES:
        msg = push_send.build_daily_message(plan, athlete, today)
        if not msg:
            print(f"  {athlete}: hviledag — ingen push.")
            continue
        payload = json.dumps(msg, ensure_ascii=False)
        for s in push_send.subs_for_athlete(subs, athlete):
            res = sender(s, payload)
            if res is True:
                sent += 1
            elif res == "dead" or (isinstance(res, int) and push_send.is_dead_status(res)):
                dead.add(s["endpoint"])
                print(f"  {athlete}: død subscription fjernes ({res}).")
            else:
                print(f"  {athlete}: push-fejl (ikke-blokerende): {res}")
    pruned = push_send.prune_subscriptions(subs, dead) if dead else None
    print(f"Sendt: {sent} · døde: {len(dead)}")
    return sent, dead, pruned


def run_send_evening(subs, sender):
    """Aften-gren: fast AF-check-in-påmindelse, kun til Kennet.

    Samme død-håndtering/prune-kontrakt som run_send, men uafhængig af plan.json
    (beskeden er statisk). Returnerer (sent, dead, pruned_or_None).
    """
    dead = set()
    sent = 0
    payload = json.dumps(AF_EVENING_MSG, ensure_ascii=False)
    for s in push_send.subs_for_athlete(subs, "kennet"):
        res = sender(s, payload)
        if res is True:
            sent += 1
        elif res == "dead" or (isinstance(res, int) and push_send.is_dead_status(res)):
            dead.add(s["endpoint"])
            print(f"  kennet: død subscription fjernes ({res}).")
        else:
            print(f"  kennet: push-fejl (ikke-blokerende): {res}")
    pruned = push_send.prune_subscriptions(subs, dead) if dead else None
    print(f"Aften-reminder sendt: {sent} · døde: {len(dead)}")
    return sent, dead, pruned


def _webpush_sender(s, payload):
    """Produktions-sender: pywebpush med VAPID.

    Isolerer ALLE fejl pr. subscription — én dårlig subscription må aldrig
    vælte hele batchen. Returnerer:
      True   = sendt
      int    = HTTP-status (kalder vurderer død via is_dead_status)
      "dead" = ugyldig subscription (fx korrupt base64-nøgle) => skal fjernes
      False  = midlertidig/ukendt fejl (beholdes, prøves igen næste gang)
    """
    try:
        webpush(
            subscription_info={"endpoint": s["endpoint"], "keys": s["keys"]},
            data=payload,
            vapid_private_key=VAPID_PRIVATE,
            vapid_claims={"sub": VAPID_SUBJECT},
        )
        return True
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        return code if code else False
    except (ValueError, KeyError, TypeError) as e:
        # Korrupt subscription (ugyldig base64-nøgle, manglende felt osv.).
        # Kaster FØR afsendelse — behandl som død, så den ryddes.
        print(f"    ugyldig subscription ({type(e).__name__}) — markeres død")
        return "dead"


def main():
    if webpush is None:
        print("pywebpush ikke installeret — afbryder."); return 1
    if not VAPID_PRIVATE:
        print("VAPID_PRIVATE mangler — afbryder."); return 1

    mode = os.environ.get("PUSH_MODE", "daily").strip().lower()

    subs_sha, subs = _load_subscriptions()
    if not subs:
        print("Ingen subscriptions — intet at sende."); return 0

    today = str(date.today())

    if mode == "evening":
        print("Mode: evening (AF-check-in)")
        _sent, dead, pruned = run_send_evening(subs, _webpush_sender)
    else:
        print("Mode: daily")
        _psha, plan_raw = _gh_get_raw(REPO, "data/plan.json", GH_TOKEN)
        if not plan_raw:
            print("Kunne ikke hente plan.json — afbryder."); return 1
        plan = json.loads(plan_raw)
        _sent, dead, pruned = run_send(plan, subs, today, _webpush_sender)

    if dead and pruned is not None:
        _gh_put(PRIVATE_REPO, SUBS_PATH, subs_sha,
                json.dumps({"subscriptions": pruned}, ensure_ascii=False, indent=2),
                f"push: fjernet {len(dead)} døde subscriptions {today}",
                PRIVATE_TOKEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
