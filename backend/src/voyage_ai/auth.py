"""Supabase JWT verification and the explicit local-development identity."""

from __future__ import annotations

from dataclasses import dataclass
import os
from uuid import UUID

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

_bearer = HTTPBearer(auto_error=False)
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None = None


def _local_development_mode() -> bool:
    environment = os.getenv("VOYAGEAI_ENV", "development").casefold()
    return environment in {"development", "dev"} and not os.getenv("RENDER")


def _configured_url() -> str | None:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/") or None


def _decode_asymmetric_token(token: str, issuer: str, algorithm: str) -> dict:
    jwks_url = f"{issuer}/.well-known/jwks.json"
    client = _jwks_clients.get(jwks_url)
    if client is None:
        client = jwt.PyJWKClient(jwks_url, cache_keys=True, timeout=8)
        _jwks_clients[jwks_url] = client
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=[algorithm],
        audience="authenticated",
        issuer=issuer,
        options={"require": ["exp", "sub"]},
    )


def _decode_legacy_hs256(token: str, issuer: str) -> dict | AuthenticatedUser:
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    if jwt_secret:
        return jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            issuer=issuer,
            options={"require": ["exp", "sub"]},
        )

    # Supabase recommends server-side /auth/v1/user validation for legacy
    # shared-secret access tokens when the secret is not configured here.
    anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    if not anon_key:
        raise HTTPException(status_code=503, detail="Supabase token verification is not configured.")
    try:
        response = httpx.get(
            f"{issuer}/user",
            headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
            timeout=8,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Authentication is required.")
        user = response.json()
        return AuthenticatedUser(id=str(UUID(user["id"])), email=user.get("email"))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=503, detail="Supabase authentication is temporarily unavailable.") from error


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    project_url = _configured_url()
    if not project_url:
        if _local_development_mode():
            return AuthenticatedUser(id="00000000-0000-4000-8000-000000000001", email="local@voyageai.test")
        raise HTTPException(status_code=503, detail="Supabase authentication is not configured.")

    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication is required.", headers={"WWW-Authenticate": "Bearer"})

    issuer = f"{project_url}/auth/v1"
    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm == "HS256":
            claims_or_user = _decode_legacy_hs256(token, issuer)
            if isinstance(claims_or_user, AuthenticatedUser):
                return claims_or_user
            claims = claims_or_user
        elif algorithm in {"ES256", "RS256"}:
            claims = _decode_asymmetric_token(token, issuer, algorithm)
        else:
            raise HTTPException(status_code=401, detail="Authentication token is invalid.")
        subject = str(UUID(claims["sub"]))
        return AuthenticatedUser(id=subject, email=claims.get("email"))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=401, detail="Authentication token is invalid or expired.", headers={"WWW-Authenticate": "Bearer"}) from error
