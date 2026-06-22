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
parts.append("Du er en uafhængig teknisk QA-agent for 'Fast as Fifty' systemet. Vær konkret og direkte. Svar på dansk. Max 600 ord.\n")

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
1. KONKRETE FEJL i koden (forkerte URL'er, manglende exit codes, encoding, race conditions)
2. SIKKERHEDSRISICI (token-lækage, for brede permissions)
3. TOP 3 FORBEDRINGER (specifik fil + linje + hvad der skal ændres)
4. HVAD ER SOLIDT (rør ikke ved dette)

Vær kortfattet. Max 600 ord.
""")

prompt = "\n".join(parts)

# Kald Anthropic API
payload = json.dumps({
    "model": "claude-sonnet-4-6",
    "max_tokens": 2000,
    "system": "Du er en kritisk teknisk QA-agent. Svar på dansk.",
    "messages": [{"role": "user", "content": prompt}]
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.anthropic.com/v1/messages",
    data=payload,
    method="POST",
    headers={
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "x-api-key": ANTHROPIC_KEY,
    }
)

with urllib.request.urlopen(req, timeout=60) as resp:
    result = json.loads(resp.read())
    report = result["content"][0]["text"]

print("=" * 60)
print("QA SUB-AGENT RAPPORT")
print("=" * 60)
print(report)
print("=" * 60)
