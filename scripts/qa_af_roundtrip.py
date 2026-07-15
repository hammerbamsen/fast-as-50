# -*- coding: utf-8 -*-
"""Fortryd: nulstil Alkohol til None, og test derefter feltnavnene korrekt.

Den forrige version skrev Alkohol=0 hvor feltet var tomt — altså registrerede
den en AF-dag Kennet ikke selv havde logget. Det rulles tilbage her.
Derefter valideres protein/motivation/fatigue med en skriv-og-ryd-igen-cyklus.
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
FIELDS = ("Alkohol", "protein", "motivation", "fatigue")
L = []

def snap():
    r = requests.get(f"{BASE}/wellness/{TODAY}", auth=AUTH, timeout=30)
    return {k: r.json().get(k) for k in FIELDS} if r.status_code == 200 else None

L.append(f"FOER: {snap()}")

# 1) Rul den utilsigtede skrivning tilbage
p = requests.put(f"{BASE}/wellness/{TODAY}", auth=AUTH, json={"Alkohol": None}, timeout=30)
L.append(f"NULSTIL Alkohol -> HTTP {p.status_code}")
L.append(f"  efter nulstilling: {snap()}")

# 2) Valider de tre feltnavne: skriv testvaerdi, tjek 200, ryd igen
for f in ("protein", "motivation", "fatigue"):
    w = requests.put(f"{BASE}/wellness/{TODAY}", auth=AUTH, json={f: 1}, timeout=30)
    ok = w.status_code == 200
    c = requests.put(f"{BASE}/wellness/{TODAY}", auth=AUTH, json={f: None}, timeout=30)
    L.append(f"  {f:11} skriv->{w.status_code} ryd->{c.status_code}  {'✅ accepteret' if ok else '❌ AFVIST: '+w.text[:120]}")

# 3) Kontrolproeve: forkert navn SKAL give 422
b = requests.put(f"{BASE}/wellness/{TODAY}", auth=AUTH, json={"Protein": 1}, timeout=30)
L.append(f"  {'Protein':11} (gammelt navn) -> HTTP {b.status_code} {'✅ afvises som forventet' if b.status_code == 422 else '⚠️ uventet'}")

L.append(f"EFTER: {snap()}")
out = "\n".join(L) + "\n"
print(out)
path = "debug/qa_af_roundtrip.txt"
g = requests.get(f"https://api.github.com/repos/{PUB}/contents/{path}",
                 headers={"Authorization": f"Bearer {GTOK}"}, timeout=30)
body = {"message": "qa: af roundtrip v2 + rollback", "content": base64.b64encode(out.encode()).decode()}
if g.status_code == 200:
    body["sha"] = g.json()["sha"]
requests.put(f"https://api.github.com/repos/{PUB}/contents/{path}",
             headers={"Authorization": f"Bearer {GTOK}"}, json=body, timeout=30)
