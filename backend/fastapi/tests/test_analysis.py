"""Analysis API: storage, live preview, unavailable AI and safe failure."""

import asyncio
import uuid

import pytest

from app.models import AnalysisResult, ECGChunk, KnownSession

from conftest import SESSION_ID, bearer, issue_user_token


def _token(role="operator", user_id=2):
    return bearer(issue_user_token(user_id, role))


def _add_chunks(session_factory, *, status="completed", samples=None):
    from test_dsp import synthetic_ecg

    values = samples or synthetic_ecg(bpm=72, seconds=6)

    async def _create():
        async with session_factory() as session:
            known = await session.get(KnownSession, SESSION_ID)
            known.status = status
            session.add(
                ECGChunk(
                    id=uuid.uuid4(),
                    session_id=SESSION_ID,
                    device_id=known.device_id,
                    start_time=known.registered_at,
                    sample_rate_hz=200,
                    samples=values,
                    sample_count=len(values),
                    chunk_index=0,
                )
            )
            await session.commit()

    asyncio.run(_create())


def _first_analysis(session_factory):
    async def _read():
        async with session_factory() as session:
            rows = list(await session.scalars(select(AnalysisResult)))
            return rows

    from sqlalchemy import select

    return asyncio.run(_read())


def test_analysis_runs_stores_and_is_returned(scoped_client, known_session, session_factory):
    _add_chunks(session_factory)

    response = scoped_client.post(
        f"/sessions/{known_session}/analysis", headers=_token()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["signal"]["quality"]["usable"] is True
    assert body["measurements"]["heart_rate_bpm"] is not None
    assert body["analysis_version"] == 1
    # No model is bundled, so this must be an explicit unavailability - not a
    # fabricated class or probability.
    assert body["ai"]["available"] is False
    assert body["ai"]["predicted_class"] is None
    assert body["ai"]["probabilities"] is None
    assert body["ai"]["reason"]

    stored = scoped_client.get(
        f"/sessions/{known_session}/analysis", headers=_token()
    )
    assert stored.status_code == 200
    assert stored.json()["analysis_version"] == 1

    assert len(_first_analysis(session_factory)) == 1


def test_analysis_is_refused_while_the_session_is_active(
    scoped_client, known_session, session_factory
):
    _add_chunks(session_factory, status="active")

    response = scoped_client.post(
        f"/sessions/{known_session}/analysis", headers=_token()
    )

    assert response.status_code == 409
    assert response.json()["code"] == "session_active"


def test_live_analysis_does_not_persist(scoped_client, known_session, session_factory):
    _add_chunks(session_factory, status="active")

    response = scoped_client.get(
        f"/sessions/{known_session}/analysis/live", headers=_token()
    )

    assert response.status_code == 200
    assert response.json()["analysis_version"] == 0
    assert _first_analysis(session_factory) == []


def test_analysis_without_chunks_is_unusable(scoped_client, known_session, session_factory):
    async def _complete():
        async with session_factory() as session:
            known = await session.get(KnownSession, SESSION_ID)
            known.status = "completed"
            await session.commit()

    asyncio.run(_complete())

    response = scoped_client.post(
        f"/sessions/{known_session}/analysis", headers=_token()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unusable"
    assert body["measurements"]["heart_rate_bpm"] is None
    assert body["signal"]["quality"]["reasons"]


def test_analysis_requires_a_user_token(scoped_client, known_session, session_factory):
    _add_chunks(session_factory)

    assert scoped_client.post(f"/sessions/{known_session}/analysis").status_code == 401


def test_analysis_is_404_for_an_unknown_session(scoped_client, unregistered_session_id):
    response = scoped_client.post(
        f"/sessions/{unregistered_session_id}/analysis", headers=_token()
    )

    assert response.status_code == 404


@pytest.mark.parametrize("role", ["operator", "admin"])
def test_both_operator_roles_can_run_analysis(
    scoped_client, known_session, session_factory, role
):
    _add_chunks(session_factory, status="active")

    response = scoped_client.get(
        f"/sessions/{known_session}/analysis/live",
        headers=_token(role, 7),
    )
    assert response.status_code == 200


def test_ai_output_is_exposed_only_when_the_model_produces_it(
    scoped_client, known_session, session_factory, monkeypatch
):
    from app.inference import InferenceResult
    import app.analysis as analysis_module

    class FakeService:
        def predict(self, analysis):
            return InferenceResult(
                available=True,
                model_name="test-lr",
                model_version="0.1.0",
                classes=["Normal", "AFib", "Other", "Noisy"],
                predicted_class="Normal",
                probabilities={"Normal": 0.7, "AFib": 0.1, "Other": 0.1, "Noisy": 0.1},
                analyzed_at="2026-10-28T10:00:00Z",
            )

    monkeypatch.setattr(analysis_module, "get_inference_service", lambda: FakeService())
    _add_chunks(session_factory)

    response = scoped_client.post(
        f"/sessions/{known_session}/analysis", headers=_token()
    )

    assert response.status_code == 200
    ai = response.json()["ai"]
    assert ai["available"] is True
    assert ai["predicted_class"] == "Normal"
    assert ai["probabilities"]["Normal"] == 0.7
    assert ai["model_version"] == "0.1.0"
