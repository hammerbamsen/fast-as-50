# -*- coding: utf-8 -*-
"""Engangs-diagnostik: rapportér indhold af push_subscriptions.json i det private repo."""
import base64, json, os
import requests

REPO = os.environ.get("PRIVATE_REPO", "")
TOKEN = os.environ.get("PRIVATE_REPO_TOKEN", "")
r = requests.get(f"https://api.github.com/repos/{REPO}/contents/push_subscriptions.json",
                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}, timeout=30)
if r.status_code == 404:
    print("push_subscriptions.json findes ikke (0 subscriptions) — ren.")
elif r.status_code == 200:
    subs = json.loads(base64.b64decode(r.json()["content"]).decode()).get("subscriptions", [])
    print(f"Subscriptions i store: {len(subs)}")
    for s in subs:
        ep = s.get("endpoint","")
        tag = "FAKE-TEST" if "TEST-DIAG" in ep else "ægte"
        print(f"  [{tag}] {s.get('athlete')} · ...{ep[-24:]}")
else:
    print(f"Uventet status: {r.status_code}")
