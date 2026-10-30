"""Analysis endpoints.

Two modes:

* ``POST /sessions/{id}/analysis`` runs DSP + CNN classification + AI advisory
  and stores a versioned result plus a queryable ``ml_predictions`` row. It is
  refused while the session is active.
* ``GET /sessions/{id}/analysis/live`` computes the same DSP measurements on the
  stored chunks without persisting anything and without running the CNN or the
  advisor, so the monitor can poll it every few seconds.

All endpoints require a user token and go through the same viewer check as the
waveform reads.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.analysis import run_analysis
from app.core.security import UserPrincipal, require_user
from app.db import get_session
from app.errors import APIError
from app.models import AnalysisResult, ECGChunk, KnownSession, MLPrediction, SimulationRun
from app.registry import require_viewer
from app.schemas import (
    AnalysisResponse,
    MLPredictionListResponse,
    MLPredictionRecord,
)

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


async def _simulation_context(
    session: AsyncSession, session_id: uuid.UUID
) -> dict | None:
    """Provenance for a recording the built-in simulator produced.

    Read from the latest `simulation_runs` row rather than from the in-memory
    manager, so the label survives a restart and is available when the analysis
    runs after the stream has stopped.
    """
    run = await session.scalar(
        select(SimulationRun)
        .where(SimulationRun.session_id == session_id)
        .order_by(SimulationRun.started_at.desc())
        .limit(1)
    )
    if run is None:
        return None
    return {
        "kind": "csv" if run.scenario == "csv" else "scenario",
        "scenario": run.scenario,
        "label": run.label,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "stopped_at": run.stopped_at.isoformat() if run.stopped_at else None,
        "chunks_sent": run.chunks_sent,
    }


def _prediction_row(
    *,
    session_id: uuid.UUID,
    analysis_result_id: uuid.UUID,
    version: int,
    payload: dict,
    created_at: datetime,
) -> MLPrediction:
    """Project the stored JSON payload into the queryable ML record."""

    ml = payload.get("ml") or {}
    advice = payload.get("advice") or {}
    signal = payload.get("signal") or {}
    quality = signal.get("quality") or {}
    measurements = payload.get("measurements") or {}

    return MLPrediction(
        session_id=session_id,
        analysis_result_id=analysis_result_id,
        analysis_version=version,
        model_name=(ml.get("model_name") or None),
        model_version=(ml.get("model_version") or None),
        model_sha256=(ml.get("model_sha256") or None),
        predicted_class=(ml.get("predicted_class") or None),
        predicted_label=(ml.get("predicted_label") or None),
        confidence=ml.get("confidence"),
        quality_score=quality.get("score"),
        heart_rate_bpm=measurements.get("heart_rate_bpm"),
        window_count=int(ml.get("window_count") or 0),
        signal_duration_seconds=signal.get("duration_seconds"),
        advisor_provider=(advice.get("provider") or None),
        advice_risk_level=(advice.get("risk_level") or None),
        ml=ml,
        advice=advice,
        created_at=created_at,
    )


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
    simulation = await _simulation_context(session, session_id)
    # DSP scanning and a CPU CNN pass are blocking work. Running them on the
    # event loop would stall every websocket and ingest request for the
    # duration of the analysis.
    payload = await run_in_threadpool(
        run_analysis,
        str(session_id),
        chunks,
        simulation=simulation,
        include_ml=True,
        include_advice=True,
    )

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
        model_version=(payload.get("ml") or {}).get("model_version"),
        analysis=payload,
    )
    session.add(record)
    await session.flush()

    created_at = datetime.now(timezone.utc)
    session.add(
        _prediction_row(
            session_id=session_id,
            analysis_result_id=record.id,
            version=version,
            payload=payload,
            created_at=created_at,
        )
    )
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

    This is intentionally the same DSP as the stored analysis. The CNN and the
    advisory are skipped: polling them every four seconds would burn CPU and,
    once a real AI API is connected, API quota. Nothing is written, so polling
    never creates a version, a prediction row or a duplicate report.
    """
    await require_viewer(session, session_id, user)
    chunks = await _chunks(session, session_id)
    simulation = await _simulation_context(session, session_id)
    payload = await run_in_threadpool(
        run_analysis,
        str(session_id),
        chunks,
        simulation=simulation,
        include_ml=False,
        include_advice=False,
    )
    payload["analysis_version"] = 0
    payload["session_id"] = str(session_id)
    return AnalysisResponse(**payload)


@router.get(
    "/sessions/{session_id}/ml-predictions",
    response_model=MLPredictionListResponse,
)
async def list_ml_predictions(
    session_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> MLPredictionListResponse:
    """Every stored classification/advisory run for a session, newest first.

    This is the audit/history view of the storage the analysis pipeline writes.
    It is also the endpoint a future "regenerate advice" action can read.
    """
    await require_viewer(session, session_id, user)
    rows = list(
        await session.scalars(
            select(MLPrediction)
            .where(MLPrediction.session_id == session_id)
            .order_by(MLPrediction.created_at.desc())
            .limit(limit)
        )
    )
    return MLPredictionListResponse(
        session_id=session_id,
        count=len(rows),
        predictions=[
            MLPredictionRecord(
                id=row.id,
                session_id=row.session_id,
                analysis_version=row.analysis_version,
                created_at=row.created_at,
                model_name=row.model_name,
                model_version=row.model_version,
                model_sha256=row.model_sha256,
                predicted_class=row.predicted_class,
                predicted_label=row.predicted_label,
                confidence=row.confidence,
                quality_score=row.quality_score,
                heart_rate_bpm=row.heart_rate_bpm,
                window_count=row.window_count,
                signal_duration_seconds=row.signal_duration_seconds,
                advisor_provider=row.advisor_provider,
                advice_risk_level=row.advice_risk_level,
                ml=row.ml or {},
                advice=row.advice or {},
            )
            for row in rows
        ],
    )
