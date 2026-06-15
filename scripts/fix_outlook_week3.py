import os, requests, json

CLIENT_ID     = os.environ['AZURE_CLIENT_ID']
TENANT_ID     = os.environ['AZURE_TENANT_ID']
CLIENT_SECRET = os.environ['AZURE_CLIENT_SECRET']

# Hent token
r = requests.post(f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token", data={
    "grant_type": "client_credentials",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scope": "https://graph.microsoft.com/.default"
})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
GRAPH = "https://graph.microsoft.com/v1.0/me"

# Slet forkerte events (tirs svøm + ons cykel bjerg)
delete_ids = [
    "AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0A92vJr1v2DEWwUBmIY0fowAAF3nPpPAAA",  # Svøm tirs
    "AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0A92vJr1v2DEWwUBmIY0fowAAF3nPpQwAA",  # Cykel bjerg ons
]
for eid in delete_ids:
    r = requests.delete(f"{GRAPH}/events/{eid}", headers=H)
    print(f"Slet {eid[:30]}...: {r.status_code}")

# Opret korrekte events
events = [
    {
        "subject": "Cykel Formentor 149km",
        "body": {"contentType": "text", "content": "Lang cykeltur Mallorca — Formentor-ruten.\n- Z2 base hele turen\n- Husk energi og væske"},
        "start": {"dateTime": "2026-06-16T06:00:00", "timeZone": "Europe/Copenhagen"},
        "end":   {"dateTime": "2026-06-16T12:00:00", "timeZone": "Europe/Copenhagen"},
        "categories": ["Træning"],
        "showAs": "busy"
    },
    {
        "subject": "Svøm 1500m let teknisk",
        "body": {"contentType": "text", "content": "- 400m varm-op Z1\n5x\n- 100m teknik Z1-Z2\n- 300m cool"},
        "start": {"dateTime": "2026-06-17T06:00:00", "timeZone": "Europe/Copenhagen"},
        "end":   {"dateTime": "2026-06-17T06:45:00", "timeZone": "Europe/Copenhagen"},
        "categories": ["Træning"],
        "showAs": "busy"
    },
]
for ev in events:
    r = requests.post(f"{GRAPH}/events", headers=H, json=ev)
    print(f"Opret '{ev['subject']}': {r.status_code}")
    if r.status_code == 201:
        print("  ✅ OK")
    else:
        print(f"  ❌ {r.text[:200]}")
