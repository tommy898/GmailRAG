import os
import uuid
from typing import Annotated


import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


_bearer_scheme = HTTPBearer(auto_error=False)
_jwks_client: PyJWKClient | None = None


class InvalidAccessTokenError(Exception):
    pass


def get_supabase_url() -> str:
    supabase_url = os.environ.get("SUPABASE_URL")

    if not supabase_url:
        raise RuntimeError("SUPABASE_URL environment variable is not set")

    return supabase_url.rstrip("/")


def get_supabase_issuer() -> str:
    return f"{get_supabase_url()}/auth/v1"


def get_jwks_client() -> PyJWKClient:
    global _jwks_client

    if _jwks_client is None:
        jwks_url = f"{get_supabase_issuer()}/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url)

    return _jwks_client


def verify_supabase_access_token(token: str) -> uuid.UUID:
    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(token)

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=get_supabase_issuer(),
            options={
                "require": ["sub", "exp", "iss", "aud"],
            },
        )

        if claims.get("role") != "authenticated":
            raise InvalidAccessTokenError(
                "Token does not represent an authenticated user"
            )

        return uuid.UUID(claims["sub"])

    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidAccessTokenError(
            "Invalid Supabase access token"
        ) from exc


def get_current_profile_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ],
) -> uuid.UUID:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return verify_supabase_access_token(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
