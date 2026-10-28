"""Built-in simulator endpoints.

The dashboard drives the simulator through these calls:

* `GET  /simulator/scenarios`            - the picker's choices;
* `POST /sessions/{id}/simulation`       - start a scenario on an active session;
* `POST /sessions/{id}/replay`           - replay an uploaded CSV into it;
* `POST /sessions/{id}/simulation/stop`  - stop it;
* `GET  /sessions/{id}/simulation`       - what is (or was) running.

They are user endpoints, not device endpoints: an operator who can already start
a recording and mint a device token is not gaining a new capability by asking
the server to stream a scenario. The samples that result are still stamped with
the session's own device id and go through the normal ingestion handlers - see
`app/simulation/manager.py`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import UserPrincipal, require_user
from app.db import get_session
from app.errors import APIError
from app.registry import ACTIVE, require_viewer
from app.schemas import (
    ReplayStartedResponse,
    ScenarioInfo,
    SimulationStartRequest,
    SimulationStatusResponse,
)
from app.simulation.csv_source import parse_csv
from app.simulation.manager import SimulationConflict, manager
from app.simulation.scenarios import SCENARIOS, get_scenario

router = APIRouter(tags=["simulation"])


@router.get("/simulator/scenarios", response_model=list[ScenarioInfo])
async def list_scenarios(
    user: UserPrincipal = Depends(require_user),
) -> list[ScenarioInfo]:
    """Every rhythm the built-in simulator can stream."""
    return [ScenarioInfo(**scenario.as_dict()) for scenario in SCENARIOS.values()]


@router.post(
    "/sessions/{session_id}/simulation",
    response_model=SimulationStatusResponse,
    status_code=201,
)
async def start_simulation(
    session_id: uuid.UUID,
    payload: SimulationStartRequest,
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> SimulationStatusResponse:
    known = await require_viewer(session, session_id, user)
    if known.status != ACTIVE:
        raise APIError(
            status_code=409,
            detail=(
                "Simulation needs an active recording: start a session first, "
                "then stream a scenario into it."
            ),
            code="session_not_active",
        )

    try:
        scenario = get_scenario(payload.scenario)
    except KeyError as exc:
        raise APIError(
            status_code=422,
            detail=exc.args[0] if exc.args else "Unknown scenario.",
            code="validation_error",
            errors=[
                {
                    "field": "scenario",
                    "message": f"expected one of {sorted(SCENARIOS)}",
                }
            ],
        ) from exc

    try:
        await manager.start(
            session_id,
            scenario.key,
            payload.duration_seconds,
            known.device_id,
        )
    except SimulationConflict as exc:
        raise APIError(
            status_code=409, detail=str(exc), code="simulation_conflict"
        ) from exc

    return SimulationStatusResponse(**await manager.status(session_id))


@router.post(
    "/sessions/{session_id}/simulation/stop",
    response_model=SimulationStatusResponse,
)
async def stop_simulation(
    session_id: uuid.UUID,
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> SimulationStatusResponse:
    """Stop the stream. Stopping an idle session is not an error."""
    await require_viewer(session, session_id, user)
    await manager.stop(session_id)
    return SimulationStatusResponse(**await manager.status(session_id))


@router.get(
    "/sessions/{session_id}/simulation",
    response_model=SimulationStatusResponse,
)
async def simulation_status(
    session_id: uuid.UUID,
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> SimulationStatusResponse:
    """The running run, or the most recent finished one for this session."""
    await require_viewer(session, session_id, user)
    return SimulationStatusResponse(**await manager.status(session_id))


#: One CSV upload, in bytes. Deliberately larger than the JSON limit: a few
#: minutes of 200 Hz data is a megabyte or two of text, and the file is read as
#: the raw request body rather than as a JSON string.
MAX_CSV_BYTES = 20 * 1024 * 1024


@router.post(
    "/sessions/{session_id}/replay",
    response_model=ReplayStartedResponse,
    status_code=201,
)
async def replay_csv(
    session_id: uuid.UUID,
    request: Request,
    name: str | None = Query(default=None, max_length=120),
    rate_hz: float = Query(default=200.0, ge=40.0, le=2000.0),
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> ReplayStartedResponse:
    """Replay an uploaded CSV into an active session, one second at a time.

    The body is the CSV itself (`Content-Type: text/csv`), not JSON, so a file
    picker can send it unchanged. It is parsed to 200 Hz millivolt samples, and
    from then on it takes the same path as a device: the live socket announces
    each chunk, the chart fetches it, and the analysis can read it when the
    recording stops.
    """
    known = await require_viewer(session, session_id, user)
    if known.status != ACTIVE:
        raise APIError(
            status_code=409,
            detail="Replay needs an active recording: start a session first.",
            code="session_not_active",
        )

    body = await request.body()
    if not body:
        raise APIError(
            status_code=422,
            detail="The uploaded file is empty.",
            code="validation_error",
            errors=[{"field": "file", "message": "no bytes received"}],
        )
    if len(body) > MAX_CSV_BYTES:
        raise APIError(
            status_code=413,
            detail=f"The file is larger than {MAX_CSV_BYTES // (1024 * 1024)} MB.",
            code="payload_too_large",
        )

    try:
        parsed = parse_csv(
            body.decode("utf-8", errors="replace").lstrip("\ufeff"),
            assumed_rate_hz=rate_hz,
        )
    except ValueError as exc:
        raise APIError(
            status_code=422,
            detail=str(exc),
            code="validation_error",
            errors=[{"field": "file", "message": str(exc)}],
        ) from exc

    label = (name or "uploaded CSV").strip()[:80] or "uploaded CSV"
    try:
        await manager.start_csv(
            session_id,
            parsed.samples,
            label,
            known.device_id,
            parsed.sample_rate_hz,
        )
    except SimulationConflict as exc:
        raise APIError(
            status_code=409, detail=str(exc), code="simulation_conflict"
        ) from exc

    status = await manager.status(session_id)
    return ReplayStartedResponse(
        **{**status, "duration_seconds": parsed.duration_seconds},
        source_rate_hz=parsed.source_rate_hz,
        sample_rate_hz=parsed.sample_rate_hz,
        sample_count=parsed.sample_count,
        notes=parsed.notes,
    )
