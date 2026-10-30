"""Analysis API: storage, live preview, ML/advice unavailability and safe failure."""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.models import AnalysisResult, ECGChunk, KnownSession, MLPrediction

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


def _rows(session_factory, model):
    async def _read():
        async with session_factory() as session:
            return list(await session.scalars(select(model)))

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
    assert body["ml"]["available"] is False
    assert body["ml"]["predicted_class"] is None
    assert body["ml"]["probabilities"] is None
    assert body["ml"]["reason"]
    # The template advisor still produces cautious guidance: it explains that
    # no class is available rather than guessing one.
    assert body["advice"]["available"] is True
    assert body["advice"]["case"] == "unavailable"
    assert body["advice"]["provider"] == "template"
    assert body["advice"]["recommendations"]

    stored_response = scoped_client.get(
        f"/sessions/{known_session}/analysis", headers=_token()
    )
    assert stored_response.status_code == 200
    stored = stored_response.json()
    assert stored["analysis_version"] == 1
    assert stored["advice"]["case"] == "unavailable"

    assert len(_rows(session_factory, AnalysisResult)) == 1
    predictions = _rows(session_factory, MLPrediction)
    assert len(predictions) == 1
    record = predictions[0]
    assert record.analysis_version == 1
    assert record.predicted_class is None
    assert record.advisor_provider == "template"
    assert record.advice["case"] == "unavailable"
    assert record.ml["reason"]


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
    body = response.json()
    assert body["analysis_version"] == 0
    # The live poll deliberately skips the CNN and the advisor.
    assert body["ml"]["available"] is False
    assert "live preview" in body["ml"]["reason"].lower()
    assert body["advice"]["available"] is False
    assert _rows(session_factory, AnalysisResult) == []
    assert _rows(session_factory, MLPrediction) == []


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
    assert body["ml"]["available"] is False
    assert body["advice"]["case"] in {"unusable_signal", "unavailable"}


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


def test_ml_output_is_stored_packaged_and_advised(
    scoped_client, known_session, session_factory, monkeypatch
):
    from app.inference import MLResult
    import app.analysis as analysis_module

    class FakeService:
        def unavailable(self, reason):
            return MLResult(available=False, reason=reason)

        def predict(self, samples, sample_rate_hz):
            assert samples
            assert sample_rate_hz == 200
            return MLResult(
                available=True,
                model_name="test-cnn",
                model_version="0.1.0",
                model_sha256="abc123",
                architecture="ECGNet-1DCNN",
                device="cpu",
                classes=["N", "A", "O", "~"],
                class_labels={
                    "N": "Normal rhythm",
                    "A": "Atrial fibrillation pattern",
                    "O": "Other rhythm",
                    "~": "Noisy / unreadable",
                },
                predicted_class="N",
                predicted_label="Normal rhythm",
                confidence=0.7,
                probabilities={"N": 0.7, "A": 0.1, "O": 0.1, "~": 0.1},
                window_count=1,
                window_seconds=30.0,
                signal_duration_seconds=6.0,
                analyzed_at="2026-10-28T10:00:00Z",
            )

    monkeypatch.setattr(analysis_module, "get_inference_service", lambda: FakeService())
    _add_chunks(session_factory)

    response = scoped_client.post(
        f"/sessions/{known_session}/analysis", headers=_token()
    )

    assert response.status_code == 200
    body = response.json()
    ml = body["ml"]
    assert ml["available"] is True
    assert ml["predicted_class"] == "N"
    assert ml["probabilities"]["N"] == 0.7
    assert ml["model_version"] == "0.1.0"

    advice = body["advice"]
    assert advice["available"] is True
    assert advice["provider"] == "template"
    assert advice["case"] == "N"
    assert advice["risk_level"] == "low"
    assert advice["headline"]
    assert advice["recommendations"]
    assert advice["input"]["classification"]["predicted_class"] == "N"
    assert advice["input"]["recording"]["session_id"] == str(known_session)

    predictions = _rows(session_factory, MLPrediction)
    assert len(predictions) == 1
    assert predictions[0].predicted_class == "N"
    assert predictions[0].confidence == 0.7
    assert predictions[0].model_sha256 == "abc123"
    assert predictions[0].advice_risk_level == "low"


def test_ml_prediction_history_lists_stored_runs(
    scoped_client, known_session, session_factory
):
    _add_chunks(session_factory)

    created = scoped_client.post(
        f"/sessions/{known_session}/analysis", headers=_token()
    )
    assert created.status_code == 200

    history = scoped_client.get(
        f"/sessions/{known_session}/ml-predictions", headers=_token()
    )

    assert history.status_code == 200
    body = history.json()
    assert body["count"] == 1
    assert body["predictions"][0]["analysis_version"] == 1
    assert body["predictions"][0]["advisor_provider"] == "template"
    assert body["predictions"][0]["ml"]["available"] is False


def test_real_cnn_pipeline_runs_when_a_checkpoint_is_configured(
    scoped_client, known_session, session_factory, monkeypatch, tmp_path
):
    """End-to-end: real ECGNet weights -> stored ML -> template advice.

    The weights are untrained; this asserts the wiring, not diagnostic accuracy.
    """
    torch = pytest.importorskip("torch")
    from app.inference import MLService
    from app.ml.ecg_cnn import ECGNet
    import app.analysis as analysis_module

    model = ECGNet(4)
    checkpoint = tmp_path / "ecg_model.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "classes": ["N", "A", "O", "~"],
            "name": "integration-cnn",
            "version": "0.0.1",
        },
        checkpoint,
    )
    service = MLService(str(checkpoint), device="cpu", max_windows=2)
    assert service.status.available is True
    monkeypatch.setattr(analysis_module, "get_inference_service", lambda: service)

    _add_chunks(session_factory)
    response = scoped_client.post(
        f"/sessions/{known_session}/analysis", headers=_token()
    )

    assert response.status_code == 200
    body = response.json()
    ml = body["ml"]
    assert ml["available"] is True
    assert ml["model_name"] == "integration-cnn"
    assert ml["model_version"] == "0.0.1"
    assert ml["predicted_class"] in {"N", "A", "O", "~"}
    assert ml["predicted_label"]
    assert abs(sum(ml["probabilities"].values()) - 1.0) < 0.01
    assert ml["window_count"] >= 1

    advice = body["advice"]
    assert advice["available"] is True
    assert advice["case"] == ml["predicted_class"]
    assert advice["input"]["classification"]["predicted_class"] == ml["predicted_class"]

    predictions = _rows(session_factory, MLPrediction)
    assert len(predictions) == 1
    assert predictions[0].predicted_class == ml["predicted_class"]
    assert predictions[0].model_name == "integration-cnn"

    history = scoped_client.get(
        f"/sessions/{known_session}/ml-predictions", headers=_token()
    )
    assert history.status_code == 200
    stored = history.json()["predictions"][0]
    assert stored["predicted_class"] == ml["predicted_class"]
    assert stored["ml"]["probabilities"][stored["predicted_class"]] == pytest.approx(
        ml["probabilities"][ml["predicted_class"]]
    )
