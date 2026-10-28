"""Analysis endpoints.

Two modes:

* ``POST /sessions/{id}/analysis`` runs DSP + optional inference and stores a
  versioned result. It is refused while the session is active.
* ``GET /sessions/{id}/analysis/live`` computes the same measurements on the
  stored chunks without persisting anything, so the monitor can display a
  current heart rate and quality estimate while the recording is running.

All endpoints require a user token and go through the same viewer check as the
waveform reads.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import run_analysis
from app.core.security import UserPrincipal, require_user
from app.db import get_session
from app.errors import APIError
from app.models import AnalysisResult, ECGChunk, KnownSession
from app.registry import require_viewer
from app.schemas import AnalysisResponse

router = APIRouter(tags=["analysis"])


async def _chunks(session: AsyncSession, session_id: uuid.UUID) -> list[dict]:
    rows = list(
        await session.scalars(
            select(ECGChunk)
            .where(ECGChunk.session_id == session_id)
            .order_by(ECGChunk.chunk_index)
        )
    )
    return [
        {
            "chunk_index": row.chunk_index,
            "sample_rate_hz": row.sample_rate_hz,
            "samples": row.samples,
        }
        for row in rows
    ]


@router.post("/sessions/{session_id}/analysis", response_model=AnalysisResponse)
async def create_analysis(
    session_id: uuid.UUID,
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> AnalysisResponse:
    known = await require_viewer(session, session_id, user)
    if known.status == "active":
        raise APIError(
            status_code=409,
            detail="Stop the recording before running the analysis.",
            code="session_active",
        )

    chunks = await _chunks(session, session_id)
    payload = run_analysis(str(session_id), chunks)

    version = (
        await session.scalar(
            select(func.max(AnalysisResult.version)).where(
                AnalysisResult.session_id == session_id
            )
        )
        or 0
    ) + 1
    payload["analysis_version"] = version
    payload["session_id"] = str(session_id)

    record = AnalysisResult(
        session_id=session_id,
        version=version,
        status=payload["status"],
        model_version=(payload.get("ai") or {}).get("model_version"),
        analysis=payload,
    )
    session.add(record)
    await session.commit()
    return AnalysisResponse(**payload)


@router.get("/sessions/{session_id}/analysis", response_model=AnalysisResponse)
async def get_analysis(
    session_id: uuid.UUID,
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> AnalysisResponse:
    await require_viewer(session, session_id, user)
    record = await session.scalar(
        select(AnalysisResult)
        .where(AnalysisResult.session_id == session_id)
        .order_by(AnalysisResult.version.desc())
        .limit(1)
    )
    if record is None:
        raise APIError(
            status_code=404,
            detail="Analysis has not run for this session.",
            code="not_found",
        )
    return AnalysisResponse(**record.analysis)


@router.get("/sessions/{session_id}/analysis/live", response_model=AnalysisResponse)
async def live_analysis(
    session_id: uuid.UUID,
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> AnalysisResponse:
    """Unpersisted measurements for the monitor.

    This is intentionally the same DSP as the stored analysis. Nothing is
    written, so polling it never creates a version or a duplicate report.
    """
    await require_viewer(session, session_id, user)
    chunks = await _chunks(session, session_id)
    payload = run_analysis(str(session_id), chunks)
    payload["analysis_version"] = 0
    payload["session_id"] = str(session_id)
    return AnalysisResponse(**payload)
