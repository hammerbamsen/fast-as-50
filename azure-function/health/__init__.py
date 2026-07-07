# -*- coding: utf-8 -*-
"""GET /api/health — bekræfter at Function App kører."""
import json
import os
from datetime import datetime, timezone

import azure.functions as func


def main(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({
            "ok": True,
            "service": "fast-as-fifty-plan-edit",
            "now": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tenant_configured": bool(os.environ.get("AZURE_TENANT_ID")),
            "client_configured": bool(os.environ.get("AZURE_APP_CLIENT_ID")),
            "gh_token_configured": bool(os.environ.get("GH_TOKEN")),
            "allowed_upns_count": len([u for u in os.environ.get("ALLOWED_UPNS", "").split(",") if u.strip()]),
        }),
        status_code=200,
        mimetype="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )
