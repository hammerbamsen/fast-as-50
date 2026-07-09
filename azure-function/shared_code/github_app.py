# -*- coding: utf-8 -*-
"""
GitHub App-tokens til repository_dispatch.

Mønter et kortlivet installation access token (~1 time) ud fra App'ens
privatnøgle. Privatnøglen udløber ALDRIG → slut på PAT-fornyelse.

App Settings (Azure Function):
  GH_APP_ID                = 4259031            (ikke hemmelig)
  GH_APP_INSTALLATION_ID   = 145518829          (ikke hemmelig)
  GH_APP_PRIVATE_KEY       = <indhold af .pem>  (HEMMELIG)

Er GH_APP_PRIVATE_KEY ikke sat, signalerer enabled()=False, og kalderen
falder tilbage til det gamle PAT (GH_TOKEN) — så deploy er sikkert før
nøglen er lagt i Azure.
"""
import os
import time
from datetime import datetime, timezone

import jwt
import requests

GH_APP_ID = os.environ.get("GH_APP_ID", "4259031")
GH_APP_INSTALLATION_ID = os.environ.get("GH_APP_INSTALLATION_ID", "145518829")
GH_APP_PRIVATE_KEY = os.environ.get("GH_APP_PRIVATE_KEY", "")

# Cache så vi ikke mønter et token pr. request
_cache = {"token": None, "exp": 0}


def enabled() -> bool:
    """True hvis App-nøglen er konfigureret (ellers falder kalderen tilbage til PAT)."""
    return bool(GH_APP_PRIVATE_KEY.strip())


def _private_key() -> str:
    # Azure App Settings gemmer ofte multiline som én linje med \n-escapes
    return GH_APP_PRIVATE_KEY.replace("\\n", "\n").strip()


def _app_jwt() -> str:
    now = int(time.time())
    payload = {
        "iat": now - 60,     # lidt i fortiden mod clock-skew
        "exp": now + 540,    # 9 min (GitHub tillader max 10)
        "iss": GH_APP_ID,    # App ID som issuer
    }
    return jwt.encode(payload, _private_key(), algorithm="RS256")


def get_installation_token() -> str:
    """Returnér et gyldigt installation access token (cachet indtil ~60s før udløb)."""
    now = int(time.time())
    if _cache["token"] and _cache["exp"] - 60 > now:
        return _cache["token"]

    r = requests.post(
        f"https://api.github.com/app/installations/{GH_APP_INSTALLATION_ID}/access_tokens",
        headers={
            "Authorization": f"Bearer {_app_jwt()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    _cache["token"] = data["token"]
    exp = data.get("expires_at")
    if exp:
        _cache["exp"] = int(
            datetime.fromisoformat(exp.replace("Z", "+00:00"))
            .astimezone(timezone.utc).timestamp()
        )
    else:
        _cache["exp"] = now + 3000
    return _cache["token"]
