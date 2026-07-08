# -*- coding: utf-8 -*-
"""
U2 — gem en push-subscription i det PRIVATE repo.
Kaldes af .github/workflows/push-subscribe.yml på repository_dispatch.

Env:
  SUB_JSON            - subscription som JSON (endpoint, keys, athlete)
  PRIVATE_REPO        - "hammerbamsen/fast-as-50-private"
  PRIVATE_REPO_TOKEN  - fine-grained PAT med contents:rw på PRIVATE_REPO
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

PRIVATE_REPO = os.environ.get("PRIVATE_REPO", "")
PRIVATE_TOKEN = os.environ.get("PRIVATE_REPO_TOKEN", "")
SUB_JSON = os.environ.get("SUB_JSON", "")
SUBS_PATH = "push_subscriptions.json"

ALLOWED_ATHLETES = {"kennet", "eva"}


def _get(repo, path, token):
    r = requests.get(f"https://api.github.com/repos/{repo}/contents/{path}",
                     headers={"Authorization": f"Bearer {token}",
                              "Accept": "application/vnd.github+json"}, timeout=30)
    if r.status_code == 200:
        d = r.json()
        return d["sha"], base64.b64decode(d["content"]).decode("utf-8")
    if r.status_code == 404:
        return None, None
    r.raise_for_status()


def _put(repo, path, sha, content, message, token):
    body = {"message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode(),
            **({"sha": sha} if sha else {})}
    r = requests.put(f"https://api.github.com/repos/{repo}/contents/{path}",
                     headers={"Authorization": f"Bearer {token}",
                              "Accept": "application/vnd.github+json"},
                     json=body, timeout=30)
    return r.status_code in (200, 201)


def main():
    if not (PRIVATE_REPO and PRIVATE_TOKEN and SUB_JSON):
        print("Manglende env (PRIVATE_REPO/TOKEN/SUB_JSON) — afbryder."); return 1
    try:
        sub = json.loads(SUB_JSON)
    except ValueError:
        print("Ugyldig SUB_JSON — afbryder."); return 1

    # Validér minimalt — beskyt mod skrald i storen
    if not sub.get("endpoint") or not sub.get("keys"):
        print("Subscription mangler endpoint/keys — afbryder."); return 1
    if sub.get("athlete") not in ALLOWED_ATHLETES:
        print(f"Ukendt athlete {sub.get('athlete')!r} — afbryder."); return 1

    sha, raw = _get(PRIVATE_REPO, SUBS_PATH, PRIVATE_TOKEN)
    subs = []
    if raw:
        try:
            subs = json.loads(raw).get("subscriptions", [])
        except (ValueError, AttributeError):
            subs = []

    updated = push_send.upsert_subscription(subs, sub, today=str(date.today()))
    ok = _put(PRIVATE_REPO, SUBS_PATH, sha,
              json.dumps({"subscriptions": updated}, ensure_ascii=False, indent=2),
              f"push: subscription {sub['athlete']} {str(date.today())}",
              PRIVATE_TOKEN)
    print(f"  {'OK' if ok else 'FEJL'}: {len(updated)} subscriptions i store.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
