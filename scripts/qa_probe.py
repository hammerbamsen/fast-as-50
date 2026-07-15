# -*- coding: utf-8 -*-
"""1) READ-ONLY: dump dagens aktiviteter med alle commute-relaterede felter.
   2) Ryd testvaerdier fra wellness (protein/motivation/fatigue) — flere metoder."""
import base64, os, datetime, json
import requests
KEY=os.environ["INTERVALS_API_KEY"]; AID=os.environ.get("INTERVALS_ATHLETE_ID","i599466")
PUB=os.environ.get("GITHUB_REPOSITORY","hammerbamsen/fast-as-50"); GTOK=os.environ["GITHUB_TOKEN"]
AUTH=("API_KEY",KEY); TODAY=datetime.date.today().isoformat()
BASE=f"https://intervals.icu/api/v1/athlete/{AID}"
L=[]

# --- DEL 1: aktiviteter (kun laesning) ---
r=requests.get(f"{BASE}/activities",auth=AUTH,params={"oldest":"2026-07-14","newest":TODAY},timeout=30)
L.append(f"GET activities -> HTTP {r.status_code}")
if r.status_code==200:
    for a in r.json():
        if a.get("type") not in ("Ride","VirtualRide"): continue
        L.append(f"\n  {a.get('start_date_local','')[:16]}  {a.get('name')}  id={a.get('id')}")
        L.append(f"    type={a.get('type')}  moving={a.get('moving_time')}s  load={a.get('icu_training_load')}")
        for k in sorted(a.keys()):
            if any(t in k.lower() for t in ("commute","category","sub_type","subtype","tag","paired")):
                L.append(f"    {k} = {a[k]!r}")

# --- DEL 2: ryd mine testvaerdier ---
F=("protein","motivation","fatigue")
def snap():
    x=requests.get(f"{BASE}/wellness/{TODAY}",auth=AUTH,timeout=30)
    return {k:x.json().get(k) for k in F} if x.status_code==200 else None
L.append(f"\n\nWELLNESS FOER: {snap()}")
for label,payload in [("tom streng",{k:"" for k in F}),
                      ("nul",{k:0 for k in F}),
                      ("null igen",{k:None for k in F})]:
    p=requests.put(f"{BASE}/wellness/{TODAY}",auth=AUTH,json=payload,timeout=30)
    L.append(f"  {label:12} -> HTTP {p.status_code} | {snap()}")
    if all(v is None for v in (snap() or {"x":1}).values()): break
L.append(f"WELLNESS EFTER: {snap()}")

out="\n".join(L)+"\n"; print(out)
path="debug/qa_probe.txt"
g=requests.get(f"https://api.github.com/repos/{PUB}/contents/{path}",headers={"Authorization":f"Bearer {GTOK}"},timeout=30)
body={"message":"qa: probe","content":base64.b64encode(out.encode()).decode()}
if g.status_code==200: body["sha"]=g.json()["sha"]
requests.put(f"https://api.github.com/repos/{PUB}/contents/{path}",headers={"Authorization":f"Bearer {GTOK}"},json=body,timeout=30)
