# -*- coding: utf-8 -*-
"""
POST /api/plan-edit

Validerer Microsoft-token, tjekker at brugeren er i hvidlisten,
og videresender ændringen som repository_dispatch til GitHub.
Kennets PAT ligger som App Setting GH_TOKEN — aldrig på klienten.
"""
import json
import logging
import os

import azure.functions as func
import requests

from ..shared_code import auth
from ..shared_code import github_app


ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://hammerbamsen.github.io")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "hammerbamsen/fast-as-50")


def _cors(resp: func.HttpResponse) -> func.HttpResponse:
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    resp.headers["Access-Control-Max-Age"] = "3600"
    return resp


def _err(msg: str, code: int) -> func.HttpResponse:
    return _cors(func.HttpResponse(
        json.dumps({"error": msg}), status_code=code, mimetype="application/json"))


def main(req: func.HttpRequest) -> func.HttpResponse:
    # CORS preflight
    if req.method == "OPTIONS":
        return _cors(func.HttpResponse(status_code=204))

    # --- Auth ---
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return _err("Manglende Bearer-token", 401)
    token = auth_header[7:].strip()

    try:
        claims = auth.validate_token(token)
    except Exception as e:
        logging.warning(f"Token-validering fejlede: {e}")
        return _err(f"Ugyldigt token: {type(e).__name__}", 401)

    upn = auth.get_upn(claims)
    if not upn:
        return _err("Kunne ikke identificere bruger fra token", 401)
    if not auth.is_authorized(upn):
        logging.warning(f"Uautoriseret bruger: {upn}")
        return _err(f"Ikke autoriseret: {upn}", 403)

    # --- Payload ---
    try:
        body = req.get_json()
    except ValueError:
        return _err("Body er ikke gyldig JSON", 400)

    for k in ("action", "entryId", "requestId"):
        if not body.get(k):
            return _err(f"Manglende felt: {k}", 400)

    # --- Hent GitHub-token: App-token foretrukket, PAT som fallback ---
    try:
        if github_app.enabled():
            gh_token = github_app.get_installation_token()
            token_src = "app"
        elif GH_TOKEN:
            gh_token, token_src = GH_TOKEN, "pat"
        else:
            return _err("Hverken GH_APP_PRIVATE_KEY eller GH_TOKEN er konfigureret", 500)
    except Exception as e:
        logging.error(f"App-token fejlede: {e}")
        if GH_TOKEN:
            gh_token, token_src = GH_TOKEN, "pat-fallback"
        else:
            return _err(f"Kunne ikke hente App-token: {e}", 500)

    payload = {
        "event_type": "plan-edit",
        "client_payload": {
            "requestId": body["requestId"],
            "action": body["action"],
            "entryId": body["entryId"],
            "params": body.get("params") or {},
            "confirmedWarn": bool(body.get("confirmedWarn")),
            "actor": upn,
        }
    }

    try:
        r = requests.post(
            f"https://api.github.com/repos/{GH_REPO}/dispatches",
            headers={
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
            json=payload, timeout=30
        )
    except requests.RequestException as e:
        logging.error(f"GitHub-kald fejlede: {e}")
        return _err(f"GitHub-kald fejlede: {e}", 502)

    if r.status_code != 204:
        return _err(f"GitHub dispatch fejlede: HTTP {r.status_code} — {r.text[:200]}", 502)

    logging.info(f"Dispatch OK [{token_src}]: {upn} → {body['action']} {body['entryId'][:8]}")
    return _cors(func.HttpResponse(
        json.dumps({"ok": True, "requestId": body["requestId"], "actor": upn}),
        status_code=200, mimetype="application/json"))
