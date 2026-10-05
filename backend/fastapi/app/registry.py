"""Session registry lookup and viewer permissions.

Every write endpoint asks this module three questions, in this order:

1. Does this session exist? (no -> 404 `unknown_session`)
2. Is this device the session's device? (no -> 403)
3. Is the session active? (no -> 409 `session_not_active`)

and every read/subscribe endpoint asks one:

4. May this principal see this session? (no -> 403)

All of it is answered from `known_sessions`, a cache Django pushes to. No Django
call happens on any of these paths - that is the whole point of the registry.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import DevicePrincipal, UserPrincipal
from app.errors import APIError
from app.models import KnownSession

ACTIVE = "active"


async def get_known_session(
    session: AsyncSession, session_id: uuid.UUID
) -> KnownSession:
    known = await session.scalar(
        select(KnownSession).where(KnownSession.session_id == session_id)
    )
    if known is None:
        raise APIError(
            status_code=404,
            detail=(
                "Unknown session: this service has no record of it. "
                "It is created by Django, which pushes it here."
            ),
            code="unknown_session",
        )
    return known


async def require_active_session_for_device(
    session: AsyncSession,
    session_id: uuid.UUID,
    device: DevicePrincipal,
) -> KnownSession:
    """The gate every device write goes through."""
    known = await get_known_session(session, session_id)

    if known.device_id != device.device_id:
        raise APIError(
            status_code=403,
            detail="This session belongs to a different device.",
            code="forbidden",
        )

    if known.status != ACTIVE:
        raise APIError(
            status_code=409,
            detail=f"Session is '{known.status}', not accepting data.",
            code="session_not_active",
        )

    return known


def user_may_view(known: KnownSession, user: UserPrincipal) -> bool:
    """Who may read or subscribe to a session.

    * admin: every session.
    * doctor: sessions of patients they were assigned to when Django pushed it.
    * patient: their own sessions.
    """
    if user.role == "admin":
        return True
    if user.role == "doctor":
        return user.user_id in (known.doctor_ids or [])
    if user.role == "patient":
        return user.user_id == known.patient_id
    return False


def may_view(
    known: KnownSession, principal: DevicePrincipal | UserPrincipal
) -> bool:
    """Viewer check for both REST reads and the WebSocket."""
    if isinstance(principal, DevicePrincipal):
        return known.device_id == principal.device_id
    return user_may_view(known, principal)


async def require_viewer(
    session: AsyncSession,
    session_id: uuid.UUID,
    principal: DevicePrincipal | UserPrincipal,
) -> KnownSession:
    known = await get_known_session(session, session_id)
    if not may_view(known, principal):
        raise APIError(
            status_code=403,
            detail="You are not allowed to see this session.",
            code="forbidden",
        )
    return known
