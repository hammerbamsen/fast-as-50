"""GitHub API — læs og skriv data.json via Contents API."""
import json, base64, requests
from .config import GH_TOKEN, REPO


def gh_get(path):
    r = requests.get(f'https://api.github.com/repos/{REPO}/contents/{path}',
                     headers={'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github+json'})
    if r.status_code == 200:
        d = r.json()
        return d['sha'], base64.b64decode(d['content']).decode()
    return None, None

def gh_put(path, sha, content, message):
    r = requests.put(
        f'https://api.github.com/repos/{REPO}/contents/{path}',
        headers={'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github+json'},
        json={'message': message, 'content': base64.b64encode(content.encode()).decode(), 'sha': sha}
    )
    ok = r.status_code in (200, 201)
    print(f"  {'✅' if ok else '❌'} {path}: {r.json().get('commit',{}).get('sha','')[:7] if ok else r.text[:100]}")
    return ok
