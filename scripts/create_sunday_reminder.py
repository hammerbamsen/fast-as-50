
import requests, os, json

CLIENT_ID     = os.environ["AZURE_CLIENT_ID"]
TENANT_ID     = os.environ["AZURE_TENANT_ID"]
CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]

# Hent token
r = requests.post(f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token", data={
    "grant_type": "client_credentials",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scope": "https://graph.microsoft.com/.default"
})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

event = {
    "subject": "📊 Opdater Fast as Fifty dashboard",
    "body": {
        "contentType": "text",
        "content": "Skriv til Claude \"ugentlig opdatering\". Han trækker data fra Intervals.icu og interviewer dig på de subjektive spørgsmål (AF-dage, kost, energi, motivation, evt. skader).\n\nTakes 2-3 minutter.\n\nDerefter: send ugentlig update til Martin Kreutzer."
    },
    "start": {"dateTime": "2026-06-14T10:00:00", "timeZone": "Europe/Copenhagen"},
    "end":   {"dateTime": "2026-06-14T11:00:00", "timeZone": "Europe/Copenhagen"},
    "categories": ["Træning"],
    "isReminderOn": True,
    "reminderMinutesBeforeStart": 30,
    "recurrence": {
        "pattern": {
            "type": "weekly",
            "interval": 1,
            "daysOfWeek": ["sunday"]
        },
        "range": {
            "type": "endDate",
            "startDate": "2026-06-14",
            "endDate": "2026-09-06"
        }
    }
}

r2 = requests.post("https://graph.microsoft.com/v1.0/me/events", headers=headers, json=event)
print(f"Status: {r2.status_code}")
if r2.status_code == 201:
    print(f"✅ Tilbagevendende søndags-reminder oprettet!")
else:
    print(f"❌ {r2.text[:300]}")
