#!/usr/bin/env python3
"""
Fast as Fifty — Fase 0: OneDrive-reorg via Graph API.
Køres fra GitHub Actions (onedrive-reorg.yml) med app-only token.
Hver operation verificerer sit eget OUTPUT efter udførelse — ikke kun status.

Ops (kommasepareret via ONEDRIVE_OPS env):
  mkdir_arkiv     — opret _Arkiv i Claude-roden
  delete_outputs  — slet tom 'CLAUDE OUTPUTS' (til papirkurv)
  move_pictures   — flyt About me/Pictures -> Claude/Pictures
  flatten_aboutme — flyt 4 filer fra nested About me op, slet tom mappe
  move_fas        — flyt 'Fast as Fifty - træningsplan' -> Projects/'Fast as Fifty'
  archive         — flyt 2x gamle dashboard-xlsx + fast-as-fifty.html -> _Arkiv
"""
import os
import sys
import requests

GRAPH = "https://graph.microsoft.com/v1.0"
DRIVE = "b!l3-EhhmboESLtqZs3mskwcfYgAb0uTBJtdZFBL1IqyUao41S6zySS6Rj_0KgtpbJ"

# Item-ID'er verificeret via M365-connector 7/7-2026 — IKKE antaget
CLAUDE_ROOT   = "01Y5SFS4FNET3L5UAZYRD3LKVCR5YM2ND7"
CLAUDE_OUTPUTS = "01Y5SFS4AM7HLU2MINABEZMICTPMGGDIVQ"
ABOUTME_PARENT = "01Y5SFS4B5FDFZRE5CRZH2XOYEYZNWMRKE"   # Claude/About me
ABOUTME_NESTED = "01Y5SFS4HMOISMIYAKQBBLUE3OBQAYJVB6"   # Claude/About me/About me
PICTURES       = "01Y5SFS4GNPBBK6N6SKVHLSK3XGMRXI5FJ"
FAS_FOLDER     = "01Y5SFS4EESRNSDGISBJCJQ5UURGEHA6FS"   # Fast as Fifty - træningsplan
PROJECTS       = "01Y5SFS4HFKKYPRBKRTBC3NGRTTYYMXEQ6"

NESTED_FILES = [  # flyttes op ved flatten_aboutme
    ("about-me.md",             "01Y5SFS4DAHA6BW32YAJA3DSKD74JVC5EW"),
    ("aktuelle-prioriteter.md", "01Y5SFS4DURUBDRB2T3BEYYXEVFK4LBV2M"),
    ("stemme-eksempler.md",     "01Y5SFS4DXTP67KJQ2SVA3C43LIHGOUHVO"),
    ("Voice-Profile.md",        "01Y5SFS4C3R22SXD2GNBCJ2JKJ2DAQRU5R"),
]
ARCHIVE_FILES = [
    ("Fast_as_Fifty_Dashboard.xlsx",      "01Y5SFS4F6YHTF4WTJWRC2FVVLD35YZEVH"),
    ("Fast_as_Fifty_Dashboard_v1.1.xlsx", "01Y5SFS4ELOG7USA2CZZBZZVMXDVO4ZRHJ"),
    ("fast-as-fifty.html",                "01Y5SFS4DUEWDFTBG2UJEK7KEBLGV7LIY6"),
]

TOKEN = os.environ["GRAPH_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
FAILED = False


def item(item_id):
    return requests.get(f"{GRAPH}/drives/{DRIVE}/items/{item_id}", headers=H)


def move(item_id, new_parent, new_name=None):
    body = {"parentReference": {"id": new_parent}}
    if new_name:
        body["name"] = new_name
    return requests.patch(f"{GRAPH}/drives/{DRIVE}/items/{item_id}", headers=H, json=body)


def verify_parent(item_id, expected_parent, label):
    r = item(item_id)
    if r.status_code == 200 and r.json().get("parentReference", {}).get("id") == expected_parent:
        print(f"  VERIFICERET: {label} ligger nu i korrekt mappe")
        return True
    print(f"  FEJL-VERIFIKATION: {label} — status {r.status_code}, parent {r.json().get('parentReference', {}).get('id')}")
    return False


def fail(msg):
    global FAILED
    FAILED = True
    print(f"  FEJL: {msg}")


def op_mkdir_arkiv():
    print("[mkdir_arkiv] Opretter _Arkiv i Claude-roden")
    # Idempotent: findes den, genbrug
    r = requests.get(f"{GRAPH}/drives/{DRIVE}/items/{CLAUDE_ROOT}/children?$select=id,name", headers=H)
    for c in r.json().get("value", []):
        if c["name"] == "_Arkiv":
            print(f"  Findes allerede: {c['id']}")
            return c["id"]
    r = requests.post(f"{GRAPH}/drives/{DRIVE}/items/{CLAUDE_ROOT}/children",
                      headers=H, json={"name": "_Arkiv", "folder": {}})
    if r.status_code not in (200, 201):
        fail(f"oprettelse gav {r.status_code}: {r.text[:200]}")
        return None
    new_id = r.json()["id"]
    # Verificér output
    v = item(new_id)
    if v.status_code == 200 and v.json().get("name") == "_Arkiv" and "folder" in v.json():
        print(f"  VERIFICERET: _Arkiv oprettet, id {new_id}")
        return new_id
    fail("kunne ikke verificere _Arkiv efter oprettelse")
    return None


def get_arkiv_id():
    r = requests.get(f"{GRAPH}/drives/{DRIVE}/items/{CLAUDE_ROOT}/children?$select=id,name", headers=H)
    for c in r.json().get("value", []):
        if c["name"] == "_Arkiv":
            return c["id"]
    return None


def op_delete_outputs():
    print("[delete_outputs] Sletter tom 'CLAUDE OUTPUTS' (papirkurv)")
    # Sikkerhedstjek: mappen skal være tom
    r = requests.get(f"{GRAPH}/drives/{DRIVE}/items/{CLAUDE_OUTPUTS}/children?$select=id", headers=H)
    if r.status_code == 404:
        print("  Allerede slettet")
        return
    if r.json().get("value"):
        fail("mappen er IKKE tom — sletter ikke")
        return
    d = requests.delete(f"{GRAPH}/drives/{DRIVE}/items/{CLAUDE_OUTPUTS}", headers=H)
    if d.status_code != 204:
        fail(f"delete gav {d.status_code}")
        return
    v = item(CLAUDE_OUTPUTS)
    if v.status_code == 404:
        print("  VERIFICERET: mappen er væk (ligger i papirkurven)")
    else:
        fail(f"mappen svarer stadig med {v.status_code}")


def op_move_pictures():
    print("[move_pictures] Flytter Pictures -> Claude-roden")
    r = move(PICTURES, CLAUDE_ROOT)
    if r.status_code != 200:
        fail(f"move gav {r.status_code}: {r.text[:200]}")
        return
    if not verify_parent(PICTURES, CLAUDE_ROOT, "Pictures"):
        fail("verifikation")


def op_flatten_aboutme():
    print("[flatten_aboutme] Flytter 4 filer op og sletter nested mappe")
    ok = True
    for name, fid in NESTED_FILES:
        r = move(fid, ABOUTME_PARENT)
        if r.status_code != 200:
            fail(f"{name}: move gav {r.status_code}: {r.text[:150]}")
            ok = False
            continue
        if not verify_parent(fid, ABOUTME_PARENT, name):
            ok = False
    if not ok:
        fail("springer sletning af nested mappe over pga. fejl ovenfor")
        return
    # Nested mappe skal være tom før sletning
    r = requests.get(f"{GRAPH}/drives/{DRIVE}/items/{ABOUTME_NESTED}/children?$select=id,name", headers=H)
    rest = r.json().get("value", [])
    if rest:
        fail(f"nested mappe ikke tom ({[c['name'] for c in rest]}) — sletter ikke")
        return
    d = requests.delete(f"{GRAPH}/drives/{DRIVE}/items/{ABOUTME_NESTED}", headers=H)
    if d.status_code == 204 and item(ABOUTME_NESTED).status_code == 404:
        print("  VERIFICERET: nested 'About me' er tom og slettet")
    else:
        fail(f"sletning af nested mappe gav {d.status_code}")


def op_move_fas():
    print("[move_fas] Flytter træningsplan-mappen -> Projects/'Fast as Fifty'")
    r = move(FAS_FOLDER, PROJECTS, new_name="Fast as Fifty")
    if r.status_code != 200:
        fail(f"move gav {r.status_code}: {r.text[:200]}")
        return
    v = item(FAS_FOLDER)
    j = v.json()
    if (v.status_code == 200 and j.get("parentReference", {}).get("id") == PROJECTS
            and j.get("name") == "Fast as Fifty"):
        print("  VERIFICERET: ligger i Projects som 'Fast as Fifty' (samme item-id — sync-workflow upåvirket)")
    else:
        fail(f"verifikation: status {v.status_code}, navn {j.get('name')}")


def op_archive():
    print("[archive] Flytter 3 forældede filer -> _Arkiv")
    arkiv = get_arkiv_id()
    if not arkiv:
        fail("_Arkiv findes ikke — kør mkdir_arkiv først")
        return
    for name, fid in ARCHIVE_FILES:
        r = move(fid, arkiv)
        if r.status_code != 200:
            fail(f"{name}: move gav {r.status_code}: {r.text[:150]}")
            continue
        verify_parent(fid, arkiv, name)


OPS = {
    "mkdir_arkiv": op_mkdir_arkiv,
    "delete_outputs": op_delete_outputs,
    "move_pictures": op_move_pictures,
    "flatten_aboutme": op_flatten_aboutme,
    "move_fas": op_move_fas,
    "archive": op_archive,
}


def main():
    ops = [o.strip() for o in os.environ.get("ONEDRIVE_OPS", "").split(",") if o.strip()]
    if not ops:
        print("Ingen ops angivet"); sys.exit(1)
    unknown = [o for o in ops if o not in OPS]
    if unknown:
        print(f"Ukendte ops: {unknown}"); sys.exit(1)
    for o in ops:
        OPS[o]()
        print()
    if FAILED:
        print("MINDST ÉN OPERATION FEJLEDE — se log ovenfor")
        sys.exit(1)
    print("Alle operationer udført og verificeret")


if __name__ == "__main__":
    main()
