"""Supabase access-token validation for protected API routes."""
from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Header, HTTPException, status
from pydantic import BaseModel

from app import settings


class CurrentUser(BaseModel):
    id: str
    email: str | None = None


async def require_user(authorization: Annotated[str | None, Header()] = None) -> CurrentUser:
    # This bypass is intended only for local development. Render must use AUTH_REQUIRED=true.
    if not settings.AUTH_REQUIRED:
        return CurrentUser(id="local-dev-user", email=None)

    if not settings.SUPABASE_URL or not settings.SUPABASE_PUBLISHABLE_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase authentication is not configured on this backend.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid Supabase access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty bearer token.")

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{settings.SUPABASE_URL}/auth/v1/user",
                headers={
                    "apikey": settings.SUPABASE_PUBLISHABLE_KEY,
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth could not be reached. Retry shortly.",
        ) from exc

    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The Supabase access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth returned an unexpected response.",
        )

    try:
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Expected an object from Supabase Auth")
        user_id = body.get("id")
        email = body.get("email")
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("Missing user id")
        return CurrentUser(id=user_id, email=email if isinstance(email, str) else None)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth returned an invalid user payload.",
        ) from exc
