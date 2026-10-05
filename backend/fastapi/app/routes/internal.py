"""Internal endpoints Django calls.

Not public API: both require an admin user token, which Django mints for itself
with a short lifetime. They exist so that ingestion never has to call Django.

* `POST /internal/sessions` - upsert the session registry entry. Safe to replay:
  re-sending a session at any time repairs a stale cache.
* `POST /internal/devices/<id>/revoke` - add a device to the deny list, so a
  stateless token can be cut off before it expires.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import UserPrincipal, require_admin
from app.db import get_session
from app.models import KnownSession, RevokedDevice
from app.schemas import (
    RevokeDeviceRequest,
    RevokeDeviceResponse,
    SessionRegistration,
    SessionRegistrationResponse,
)

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/sessions", response_model=SessionRegistrationResponse)
async def register_session(
    payload: SessionRegistration,
    admin: UserPrincipal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SessionRegistrationResponse:
    """Insert or update the registry entry for one Django session.

    A SELECT then INSERT/UPDATE, not PostgreSQL's `ON CONFLICT DO UPDATE`: the
    suite runs on SQLite and this endpoint is called once per session, so a
    dialect-specific path would buy nothing and cost test coverage.
    """
    now = datetime.now(timezone.utc)
    known = await session.get(KnownSession, payload.session_id)

    if known is None:
        known = KnownSession(
            session_id=payload.session_id,
            patient_id=payload.patient_id,
            device_id=payload.device_id,
            doctor_ids=list(payload.doctor_ids),
            status=payload.status,
            updated_at=now,
        )
        session.add(known)
    else:
        known.patient_id = payload.patient_id
        known.device_id = payload.device_id
        known.doctor_ids = list(payload.doctor_ids)
        known.status = payload.status
        known.updated_at = now

    await session.commit()

    return SessionRegistrationResponse(
        session_id=payload.session_id,
        status=payload.status,
        known=True,
    )


@router.post(
    "/devices/{device_id}/revoke",
    response_model=RevokeDeviceResponse,
)
async def revoke_device(
    device_id: uuid.UUID,
    payload: RevokeDeviceRequest | None = None,
    admin: UserPrincipal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RevokeDeviceResponse:
    """Add a device to the deny list. Idempotent."""
    reason = payload.reason if payload else None

    existing = await session.get(RevokedDevice, device_id)
    if existing is not None:
        return RevokeDeviceResponse(device_id=device_id, revoked=True)

    session.add(RevokedDevice(device_id=device_id, reason=reason))
    await session.commit()

    return RevokeDeviceResponse(device_id=device_id, revoked=True)
