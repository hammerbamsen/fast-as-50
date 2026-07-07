# -*- coding: utf-8 -*-
"""
JWT-validering af Microsoft-tokens.
Validerer signatur, udløb, issuer, og audience mod App Registration.
"""
import os

import jwt
from jwt import PyJWKClient

_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        tenant = os.environ["AZURE_TENANT_ID"]
        _jwks_client = PyJWKClient(
            f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
        )
    return _jwks_client


def validate_token(token: str) -> dict:
    """
    Valider Microsoft JWT. Returnerer claims dict.
    Kaster jwt.InvalidTokenError eller subklasser ved fejl.
    """
    tenant = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_APP_CLIENT_ID"]

    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)

    # Accepter både v1 og v2 issuer, og både clientId og api://clientId som audience
    valid_audiences = [client_id, f"api://{client_id}"]
    valid_issuers = [
        f"https://sts.windows.net/{tenant}/",
        f"https://login.microsoftonline.com/{tenant}/v2.0",
    ]

    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=valid_audiences,
        options={"verify_iss": False, "require": ["exp", "iat"]},
    )

    if claims.get("iss") not in valid_issuers:
        raise jwt.InvalidTokenError(f"Ugyldig issuer: {claims.get('iss')}")

    return claims


def get_upn(claims: dict) -> str:
    """Hent brugerens UPN/email fra claims — flere felter forsøges."""
    return (claims.get("upn")
            or claims.get("preferred_username")
            or claims.get("email")
            or claims.get("unique_name")
            or "")


def is_authorized(upn: str) -> bool:
    """Tjek at brugeren er i hvidlisten (kommaseparerede emails i env)."""
    allowed = os.environ.get("ALLOWED_UPNS", "").split(",")
    allowed = [a.strip().lower() for a in allowed if a.strip()]
    return upn.lower() in allowed
