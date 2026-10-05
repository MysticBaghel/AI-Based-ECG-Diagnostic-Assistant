"""`WS /ws/sensor` - live readings for one session.

Authentication is a query-string token: browsers cannot set headers on a
WebSocket handshake and the React dashboard is the main viewer, so
`?token=<jwt>` is the only option that works natively. The token is verified
**before** the socket is accepted; on failure the socket is accepted, sent one
JSON error frame and closed with 4401/4403 so the client can tell the two cases
apart (see docs/api-contract.md section 6).

The token may be a user access token (patient, assigned doctor, admin) or a
device token for that session's device, so the simulator can watch what it is
uploading.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import (
    decode_viewer_token,
    DevicePrincipal,
    UserPrincipal,
)
from app.db import SessionFactory
from app.errors import APIError
from app.hub import hub
from app.models import KnownSession, RevokedDevice, SensorReading
from app.registry import get_known_session, may_view

logger = logging.getLogger(__name__)

router = APIRouter()

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_UNKNOWN_SESSION = 4404

SNAPSHOT_SIZE = 20


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _close_with(
    websocket: WebSocket, code: int, message: str, error_code: str
) -> None:
    """Accept, explain, close.

    Accepting first is what lets the client read the reason: a close frame sent
    before the handshake is complete is reported as a generic handshake failure.
    """
    await websocket.accept()
    await websocket.send_json(
        {"event": "error", "error": {"code": error_code, "message": message}}
    )
    await websocket.close(code=code)


@router.websocket("/ws/sensor")
async def sensor_socket(
    websocket: WebSocket,
    session_id: str | None = None,
    token: str | None = None,
) -> None:
    if not session_id or not token:
        await _close_with(
            websocket,
            WS_UNAUTHORIZED,
            "session_id and token query parameters are required.",
            "unauthorized",
        )
        return

    try:
        parsed_session_id = uuid.UUID(session_id)
    except (ValueError, TypeError):
        await _close_with(
            websocket, WS_UNAUTHORIZED, "session_id is not a UUID.", "unauthorized"
        )
        return

    try:
        principal: DevicePrincipal | UserPrincipal = decode_viewer_token(token)
    except APIError as exc:
        await _close_with(websocket, WS_UNAUTHORIZED, exc.detail, exc.code)
        return

    # The socket has no dependency injection, so `require_device`'s revocation
    # check has to be repeated here - a revoked device must not be able to watch
    # the session it can no longer upload to.
    if isinstance(principal, DevicePrincipal):
        async with SessionFactory() as revocation_session:
            revoked = await revocation_session.get(
                RevokedDevice, principal.device_id
            )
        if revoked is not None:
            await _close_with(
                websocket, WS_FORBIDDEN, "This device has been revoked.", "forbidden"
            )
            return

    async with SessionFactory() as session:
        try:
            known: KnownSession = await get_known_session(session, parsed_session_id)
        except APIError as exc:
            await _close_with(websocket, WS_UNKNOWN_SESSION, exc.detail, exc.code)
            return

        if not may_view(known, principal):
            await _close_with(
                websocket,
                WS_FORBIDDEN,
                "You are not allowed to see this session.",
                "forbidden",
            )
            return

        recent = list(
            await session.scalars(
                select(SensorReading)
                .where(SensorReading.session_id == parsed_session_id)
                .order_by(SensorReading.recorded_at.desc())
                .limit(SNAPSHOT_SIZE)
            )
        )

    channel = str(parsed_session_id)
    queue = await hub.subscribe(channel)

    try:
        await websocket.accept()
        await websocket.send_json(
            {
                "event": "snapshot",
                "session_id": channel,
                "readings": [
                    {
                        "reading_id": str(reading.id),
                        "sensor_type": reading.sensor_type,
                        "value": reading.value,
                        "unit": reading.unit,
                        "recorded_at": _as_utc(reading.recorded_at).isoformat(),
                    }
                    for reading in reversed(recent)
                ],
            }
        )

        await _pump(websocket, queue)
    except WebSocketDisconnect:
        logger.debug("Viewer disconnected from session %s", channel)
    finally:
        await hub.unsubscribe(channel, queue)


async def _pump(websocket: WebSocket, queue: asyncio.Queue) -> None:
    """Forward hub frames until the client goes away.

    Both directions are awaited at once, so a viewer that never sends anything
    still receives live frames, and a client that disconnects is noticed instead
    of being kept alive by an idle queue.
    """
    while True:
        receive_task = asyncio.create_task(websocket.receive_text())
        queue_task = asyncio.create_task(queue.get())

        done, pending = await asyncio.wait(
            {receive_task, queue_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()

        if receive_task in done:
            try:
                message = receive_task.result()
            except WebSocketDisconnect:
                return
            # No client->server requirement today. "ping" is answered so a
            # client can measure the socket without leaving it idle.
            if message.strip().lower() == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))

        if queue_task in done and not queue_task.cancelled():
            await websocket.send_json(queue_task.result())
