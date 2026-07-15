# -*- coding: utf-8 -*-
"""Ryd testvaerdier (protein/motivation/fatigue=1) fra dagens wellness.
PUT med null gav 200 men ryddede ikke. Proever flere metoder og rapporterer aerligt."""
import base64, os, datetime, json
import requests
KEY=os.environ["INTERVALS_API_KEY"]; AID=os.environ.get("INTERVALS_ATHLETE_ID","i599466")
PUB=os.environ.get("GITHUB_REPOSITORY","hammerbamsen/fast-as-50"); GTOK=os.environ["GITHUB_TOKEN"]
AUTH=("API_KEY",KEY); TODAY=datetime.date.today().isoformat()
BASE=f"https://intervals.icu/api/v1/athlete/{AID}"; F=("Alkohol","protein","motivation","fatigue")
L=[]
def snap():
    r=requests.get(f"{BASE}/wellness/{TODAY}",auth=AUTH,timeout=30)
    return {k:r.json().get(k) for k in F} if r.status_code==200 else f"HTTP {r.status_code}"
L.append(f"FOER: {snap()}")

# Metode A: PUT hele dokumentet med felterne eksplicit null
r=requests.get(f"{BASE}/wellness/{TODAY}",auth=AUTH,timeout=30)
doc=r.json()
for f in ("protein","motivation","fatigue"): doc[f]=None
a=requests.put(f"{BASE}/wellness/{TODAY}",auth=AUTH,json=doc,timeout=30)
L.append(f"A) PUT helt dokument m. null -> HTTP {a.status_code} | {snap()}")

# Metode B: POST til /wellness (upsert) med null
if any(snap()[f] is not None for f in ("protein","motivation","fatigue")):
    b=requests.post(f"{BASE}/wellness",auth=AUTH,json={"id":TODAY,"protein":None,"motivation":None,"fatigue":None},timeout=30)
    L.append(f"B) POST /wellness m. null -> HTTP {b.status_code} | {snap()}")

L.append(f"EFTER: {snap()}")
out="\n".join(L)+"\n"; print(out)
path="debug/qa_af_roundtrip.txt"
g=requests.get(f"https://api.github.com/repos/{PUB}/contents/{path}",headers={"Authorization":f"Bearer {GTOK}"},timeout=30)
body={"message":"qa: ryd testvaerdier","content":base64.b64encode(out.encode()).decode()}
if g.status_code==200: body["sha"]=g.json()["sha"]
requests.put(f"https://api.github.com/repos/{PUB}/contents/{path}",headers={"Authorization":f"Bearer {GTOK}"},json=body,timeout=30)
