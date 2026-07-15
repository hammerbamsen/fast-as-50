# -*- coding: utf-8 -*-
"""QA: end-to-end-test af AF-payloadens feltnavne mod Intervals — UDEN at ændre data.

Læser dagens wellness, sender PRÆCIS de samme værdier retur med de nye feltnavne,
og rapporterer HTTP-status. Et no-op-write: beviser at feltnavnene accepteres
uden at forurene Kennets træningshistorik.
"""
import base64, json, os, datetime
import requests

KEY = os.environ["INTERVALS_API_KEY"]
AID = os.environ.get("INTERVALS_ATHLETE_ID", "i599466")
PUB = os.environ.get("GITHUB_REPOSITORY", "hammerbamsen/fast-as-50")
GTOK = os.environ["GITHUB_TOKEN"]
AUTH = ("API_KEY", KEY)
TODAY = datetime.date.today().isoformat()
BASE = f"https://intervals.icu/api/v1/athlete/{AID}"

L = []
r = requests.get(f"{BASE}/wellness/{TODAY}", auth=AUTH, timeout=30)
L.append(f"GET wellness/{TODAY} -> HTTP {r.status_code}")
if r.status_code != 200:
    L.append(f"  krop: {r.text[:200]}")
else:
    w = r.json()
    cur = {k: w.get(k) for k in ("Alkohol", "protein", "motivation", "fatigue")}
    L.append(f"  nuvaerende vaerdier: {cur}")
    # Send NØJAGTIGT samme værdier retur — ingen ændring, kun feltnavne-validering
    payload = {k: v for k, v in cur.items() if v is not None}
    if not payload:
        payload = {"Alkohol": w.get("Alkohol") or 0}
        L.append("  (ingen vaerdier sat i dag — tester med Alkohol alene)")
    p = requests.put(f"{BASE}/wellness/{TODAY}", auth=AUTH, json=payload, timeout=30)
    L.append(f"PUT {json.dumps(payload)} -> HTTP {p.status_code}")
    if p.status_code == 200:
        L.append("  ✅ FELTNAVNE ACCEPTERET — AF-flowet vil virke")
    else:
        L.append(f"  ❌ AFVIST: {p.text[:250]}")
    # Verificér at intet blev ændret
    v = requests.get(f"{BASE}/wellness/{TODAY}", auth=AUTH, timeout=30)
    if v.status_code == 200:
        efter = {k: v.json().get(k) for k in cur}
        L.append(f"  efter: {efter}")
        L.append("  ✅ UÆNDRET" if efter == cur else f"  ⚠️ ÆNDRET! foer={cur}")

out = "\n".join(L) + "\n"
print(out)
path = "debug/qa_af_roundtrip.txt"
g = requests.get(f"https://api.github.com/repos/{PUB}/contents/{path}",
                 headers={"Authorization": f"Bearer {GTOK}"}, timeout=30)
body = {"message": "qa: af roundtrip", "content": base64.b64encode(out.encode()).decode()}
if g.status_code == 200:
    body["sha"] = g.json()["sha"]
pr = requests.put(f"https://api.github.com/repos/{PUB}/contents/{path}",
                  headers={"Authorization": f"Bearer {GTOK}"}, json=body, timeout=30)
if pr.status_code not in (200, 201):
    raise SystemExit(f"kunne ikke skrive rapport: {pr.status_code} {pr.text[:150]}")
print("rapport skrevet")
