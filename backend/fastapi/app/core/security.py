"""Local JWT verification - the trust boundary with Django.

No endpoint calls Django to find out who is asking. Django signs two kinds of
token with the shared `JWT_SIGNING_KEY`, and this module verifies both locally:

    user access token : {"token_type": "access", "user_id": 7, "role": "doctor", "exp": ...}
    device token      : {"type": "device", "device_id": "...", "owner_id": 7, "exp": ...}

Three things are deliberate:

* ``algorithms=["HS256"]`` is pinned, so a token claiming ``alg: none`` or
  ``alg: RS256`` is rejected before its signature is considered.
* ``exp`` is verified by PyJWT, and a token without one is rejected.
* The two audiences are separate dependencies: a user token on a device endpoint
  and a device token on a user endpoint are both 401s. Silently accepting either
  everywhere is how a read-only viewer token ends up able to upload.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import JWT_ALGORITHM, JWT_SIGNING_KEY
from app.db import get_session
from app.errors import APIError
from app.models import RevokedDevice

USER_ROLES = {"patient", "doctor", "admin"}
DEVICE_TOKEN_TYPE = "device"
USER_TOKEN_TYPE = "access"


@dataclass(frozen=True)
class DevicePrincipal:
    """What a verified device token tells us. Device tokens have no user."""

    device_id: uuid.UUID
    owner_id: int


@dataclass(frozen=True)
class UserPrincipal:
    """What a verified user access token tells us."""

    user_id: int
    role: str
    expires_at: datetime | None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _unauthorized(detail: str) -> APIError:
    return APIError(
        status_code=401,
        detail=detail,
        code="unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode(token: str) -> dict:
    """Verify signature, algorithm and expiry. Raises APIError(401) otherwise."""
    try:
        return jwt.decode(token, JWT_SIGNING_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Token has expired.") from exc
    except jwt.InvalidAlgorithmError as exc:
        raise _unauthorized("Token algorithm is not accepted.") from exc
    except jwt.PyJWTError as exc:
        raise _unauthorized("Token is invalid.") from exc


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("Authorization header must be 'Bearer <token>'.")
    return token.strip()


def decode_device_token(token: str) -> DevicePrincipal:
    """Verify a device token and return its principal."""
    claims = _decode(token)

    if claims.get("type") != DEVICE_TOKEN_TYPE:
        raise _unauthorized("Device token required.")
    if claims.get("token_type") == USER_TOKEN_TYPE:
        # Belt and braces: a user token never carries type=device, but the
        # message should say precisely which token was wrong.
        raise _unauthorized("Device token required.")

    raw_device_id = claims.get("device_id")
    owner_id = claims.get("owner_id")
    if not raw_device_id or owner_id is None:
        raise _unauthorized("Device token is missing device_id or owner_id.")

    try:
        device_id = uuid.UUID(str(raw_device_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise _unauthorized("Device token has a malformed device_id.") from exc

    try:
        owner_id = int(owner_id)
    except (ValueError, TypeError) as exc:
        raise _unauthorized("Device token has a malformed owner_id.") from exc

    return DevicePrincipal(device_id=device_id, owner_id=owner_id)


def decode_user_token(token: str) -> UserPrincipal:
    """Verify a user access token and return its principal."""
    claims = _decode(token)

    if claims.get("token_type") != USER_TOKEN_TYPE:
        raise _unauthorized("User access token required.")
    if claims.get("type") == DEVICE_TOKEN_TYPE:
        raise _unauthorized("User access token required.")

    user_id = claims.get("user_id")
    role = claims.get("role")
    if user_id is None or role is None:
        raise _unauthorized("User token is missing user_id or role.")
    if role not in USER_ROLES:
        raise _unauthorized(f"User token has an unknown role: {role!r}.")

    try:
        user_id = int(user_id)
    except (ValueError, TypeError) as exc:
        raise _unauthorized("User token has a malformed user_id.") from exc

    expires_at = None
    if claims.get("exp") is not None:
        expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)

    return UserPrincipal(user_id=user_id, role=role, expires_at=expires_at)


async def _reject_revoked(session: AsyncSession, device_id: uuid.UUID) -> None:
    """One primary-key lookup against the FastAPI-owned deny list."""
    revoked = await session.scalar(
        select(RevokedDevice.device_id).where(RevokedDevice.device_id == device_id)
    )
    if revoked is not None:
        raise APIError(
            status_code=403,
            detail="This device has been revoked.",
            code="forbidden",
        )


async def require_device(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DevicePrincipal:
    """Dependency for device endpoints: `Bearer <device token>`."""
    principal = decode_device_token(_bearer_token(request))
    await _reject_revoked(session, principal.device_id)
    return principal


async def require_user(request: Request) -> UserPrincipal:
    """Dependency for user endpoints: `Bearer <user access token>`."""
    return decode_user_token(_bearer_token(request))


async def require_admin(request: Request) -> UserPrincipal:
    """Dependency for the internal registry/revocation endpoints."""
    principal = decode_user_token(_bearer_token(request))
    if not principal.is_admin:
        raise APIError(
            status_code=403,
            detail="Admin role required.",
            code="forbidden",
        )
    return principal


def decode_viewer_token(token: str) -> DevicePrincipal | UserPrincipal:
    """For the WebSocket, which may be a device watching its own session.

    The socket has no header to inspect, so it is handed a token that could be
    either audience; this decides which, and the caller still has to prove it is
    allowed to see the requested session.
    """
    claims = _decode(token)
    if claims.get("type") == DEVICE_TOKEN_TYPE:
        return decode_device_token(token)
    return decode_user_token(token)
