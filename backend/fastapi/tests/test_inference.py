"""The inference interface: honest when absent, real when a model is supplied."""

import json

from app.inference import InferenceService


def _model_file(tmp_path, *, classes=("Normal", "AFib", "Other", "Noisy")):
    path = tmp_path / "model.json"
    features = ["heart_rate_bpm", "rr_std_ms", "rmssd_ms", "pnn50_percent", "quality_score"]
    path.write_text(
        json.dumps(
            {
                "name": "test-lr",
                "version": "0.1.0",
                "classes": list(classes),
                "feature_names": features,
                "mean": [75, 20, 20, 5, 80],
                "scale": [20, 20, 20, 10, 20],
                "coefficients": [
                    [0.4, -0.2, -0.1, 0.0, 0.3],
                    [-0.5, 0.4, 0.2, 0.1, -0.2],
                    [0.1, 0.1, -0.3, 0.0, 0.1],
                    [-0.2, 0.2, 0.3, 0.0, -0.2],
                ],
                "intercept": [0.1, -0.1, 0.0, 0.0],
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def _analysis(**overrides):
    base = {
        "signal": {"quality": {"usable": True, "score": 90.0}},
        "measurements": {
            "heart_rate_bpm": 72.0,
            "rr_std_ms": 18.0,
            "rmssd_ms": 22.0,
            "pnn50_percent": 6.0,
        },
    }
    base.update(overrides)
    return base


def test_no_model_is_explicitly_unavailable():
    service = InferenceService(None)
    result = service.predict(_analysis())

    assert service.status.available is False
    assert result.available is False
    assert result.predicted_class is None
    assert result.probabilities is None
    assert result.reason


def test_missing_model_file_is_unavailable(tmp_path):
    service = InferenceService(str(tmp_path / "does-not-exist.json"))

    assert service.status.available is False
    assert "not found" in service.status.reason.lower()


def test_a_valid_model_produces_probabilities_that_sum_to_one(tmp_path):
    service = InferenceService(_model_file(tmp_path))
    result = service.predict(_analysis())

    assert result.available is True
    assert result.model_name == "test-lr"
    assert result.model_version == "0.1.0"
    assert result.classes == ["Normal", "AFib", "Other", "Noisy"]
    assert result.predicted_class in result.classes
    assert result.probabilities is not None
    assert abs(sum(result.probabilities.values()) - 1.0) < 0.01
    assert result.analyzed_at is not None


def test_unusable_signal_is_not_classified_even_with_a_model(tmp_path):
    service = InferenceService(_model_file(tmp_path))
    analysis = _analysis()
    analysis["signal"]["quality"]["usable"] = False

    result = service.predict(analysis)

    assert result.available is False
    assert result.predicted_class is None
    assert "insufficient" in result.reason.lower()
