"""GitHub API — læs og skriv data.json via Contents API.

Retry + timeout på ALLE kald: en sporadisk GitHub-fejl (5xx, rate limit,
netværks-timeout) må ALDRIG resultere i en tavs 'success men skriver ikke'-
kørsel. Det var årsagen til de lange data-huller (cron kørte, men gh_get
fejlede stille → main() afbrød før skrivning). Gør Actions-cron pålidelig
som primær kilde uden Mac.
"""
import json, base64, time, requests
from .config import GH_TOKEN, REPO

_HEADERS = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github+json'}
_RETRIES = 4
_TIMEOUT = 25


def _request(method, url, **kwargs):
    """requests med retry + backoff på 5xx/rate-limit/netværksfejl."""
    last = None
    for attempt in range(_RETRIES):
        try:
            r = requests.request(method, url, headers=_HEADERS, timeout=_TIMEOUT, **kwargs)
            # 2xx/4xx (undtagen 429) er endelige svar — returnér straks
            if r.status_code < 500 and r.status_code != 429:
                return r
            print(f"  ⚠️  {method} {url.split('/contents/')[-1]} → HTTP {r.status_code}, forsøg {attempt+1}/{_RETRIES}")
            last = r
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"  ⚠️  {method} {url.split('/contents/')[-1]} → {type(e).__name__}, forsøg {attempt+1}/{_RETRIES}")
        if attempt < _RETRIES - 1:
            time.sleep(2 ** attempt)   # 1, 2, 4 s
    return last


def gh_get(path):
    r = _request('GET', f'https://api.github.com/repos/{REPO}/contents/{path}')
    if r is not None and r.status_code == 200:
        d = r.json()
        return d['sha'], base64.b64decode(d['content']).decode()
    code = r.status_code if r is not None else 'ingen svar'
    print(f"  ❌ gh_get {path}: {code} (efter {_RETRIES} forsøg)")
    return None, None


def gh_put(path, sha, content, message):
    r = _request('PUT', f'https://api.github.com/repos/{REPO}/contents/{path}',
                 json={'message': message,
                       'content': base64.b64encode(content.encode()).decode(),
                       'sha': sha})
    ok = r is not None and r.status_code in (200, 201)
    if ok:
        print(f"  ✅ {path}: {r.json().get('commit', {}).get('sha', '')[:7]}")
    else:
        code = r.status_code if r is not None else 'ingen svar'
        body = r.text[:100] if r is not None else ''
        print(f"  ❌ {path}: {code} {body} (efter {_RETRIES} forsøg)")
    return ok
