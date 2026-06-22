import os
import json
import base64
import urllib.request

GH_TOKEN = os.environ["GH_TOKEN"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
REPO = "hammerbamsen/fast-as-50"

def get_file(path):
    req = urllib.request.Request(
        "https://api.github.com/repos/{}/contents/{}".format(REPO, path),
        headers={"Authorization": "token {}".format(GH_TOKEN), "Accept": "application/vnd.github.v3+json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            d = json.loads(resp.read())
            return base64.b64decode(d["content"]).decode()
    except Exception as e:
        return "FEJL: {}".format(e)

# Saml kontekst
parts = []
parts.append("Du er en uafhaengig teknisk QA-agent for Fast as Fifty systemet. Vaer konkret og direkte. Svar paa dansk. Max 600 ord.\n")
parts.append("## WORKFLOWS\n")
for wf in ["update-kpi.yml", "build-workouts.yml", "sync-onedrive.yml", "create-outlook-events.yml"]:
    content = get_file(".github/workflows/{}".format(wf))
    parts.append("### {}\n```yaml\n{}\n```\n".format(wf, content))

parts.append("## SCRIPTS\n")
for s in ["update_kpi.py", "build_workouts.py"]:
    content = get_file("scripts/{}".format(s))
    parts.append("### {}\n```python\n{}\n```\n".format(s, content[:4000]))

parts.append("""
## DIN OPGAVE
Find og rapporter:
1. KONKRETE FEJL i koden
2. SIKKERHEDSRISICI
3. TOP 3 FORBEDRINGER (specifik fil + hvad der skal aendres)
4. HVAD ER SOLIDT

Vaer kortfattet. Max 600 ord.
""")

prompt = "\n".join(parts)

payload = json.dumps({
    "model": "claude-sonnet-4-6",
    "max_tokens": 2000,
    "system": "Du er en kritisk teknisk QA-agent. Svar paa dansk.",
    "messages": [{"role": "user", "content": prompt}]
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.anthropic.com/v1/messages",
    data=payload, method="POST",
    headers={
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "x-api-key": ANTHROPIC_KEY,
    }
)

with urllib.request.urlopen(req, timeout=90) as resp:
    result = json.loads(resp.read())
    report = result["content"][0]["text"]

# Gem rapport til fil i repoen
report_b64 = base64.b64encode(report.encode("utf-8")).decode()

# Tjek om rapport-fil eksisterer
req2 = urllib.request.Request(
    "https://api.github.com/repos/{}/contents/qa_report.txt".format(REPO),
    headers={"Authorization": "token {}".format(GH_TOKEN), "Accept": "application/vnd.github.v3+json"}
)
sha = None
try:
    with urllib.request.urlopen(req2) as resp:
        sha = json.loads(resp.read()).get("sha")
except Exception:
    pass

payload2 = {"message": "QA sub-agent rapport", "content": report_b64}
if sha:
    payload2["sha"] = sha

req3 = urllib.request.Request(
    "https://api.github.com/repos/{}/contents/qa_report.txt".format(REPO),
    data=json.dumps(payload2).encode(), method="PUT",
    headers={"Authorization": "token {}".format(GH_TOKEN), "Accept": "application/vnd.github.v3+json", "Content-Type": "application/json"}
)
with urllib.request.urlopen(req3) as resp:
    print("Rapport gemt i repo: HTTP {}".format(resp.status))

print(report)
