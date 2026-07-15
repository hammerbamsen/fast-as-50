# -*- coding: utf-8 -*-
"""Engangs-diagnostik: skriv antal+typer af subscriptions til debug/subs_status.txt i OFFENTLIGT repo."""
import base64, json, os
import requests

PRIV = os.environ.get("PRIVATE_REPO", "")
PTOK = os.environ.get("PRIVATE_REPO_TOKEN", "")
PUB = os.environ.get("GITHUB_REPOSITORY", "hammerbamsen/fast-as-50")
GTOK = os.environ.get("GITHUB_TOKEN", "")

lines = []
r = requests.get(f"https://api.github.com/repos/{PRIV}/contents/push_subscriptions.json",
                 headers={"Authorization": f"Bearer {PTOK}", "Accept": "application/vnd.github+json"}, timeout=30)
if r.status_code == 404:
    lines.append("STORE: findes ikke endnu (0 subscriptions) — ren.")
elif r.status_code == 200:
    subs = json.loads(base64.b64decode(r.json()["content"]).decode()).get("subscriptions", [])
    lines.append(f"STORE: {len(subs)} subscriptions")
    for s in subs:
        ep = s.get("endpoint", "")
        tag = "FAKE-TEST" if "TEST-DIAG" in ep else "ægte"
        lines.append(f"  [{tag}] {s.get('athlete')} ...{ep[-30:]}")
else:
    lines.append(f"STORE: uventet status {r.status_code}")

out = "\n".join(lines) + "\n"
print(out)

# Skriv til offentligt repo så det kan læses uden PAT
path = "debug/subs_status.txt"
g = requests.get(f"https://api.github.com/repos/{PUB}/contents/{path}",
                 headers={"Authorization": f"Bearer {GTOK}"}, timeout=30)
sha = g.json().get("sha") if g.status_code == 200 else None
body = {"message": "debug: subs-status", "content": base64.b64encode(out.encode()).decode()}
if sha: body["sha"] = sha
if not GTOK:
    raise SystemExit("GITHUB_TOKEN mangler i env — kan ikke skrive rapporten. "
                     "Tilfoej den til debug-subs.yml.")
_p = requests.put(f"https://api.github.com/repos/{PUB}/contents/{path}",
                  headers={"Authorization": f"Bearer {GTOK}"}, json=body, timeout=30)
if _p.status_code not in (200, 201):
    raise SystemExit(f"Kunne ikke skrive {path}: HTTP {_p.status_code} {_p.text[:200]}")
print(f"Rapport skrevet til {path}")
