"""The ML runtime: honest when absent, a real CNN pipeline when a checkpoint exists."""

import json

import pytest

from app.inference import MLService


def _synthetic_ecg(seconds: float = 6.0, fs: int = 200) -> list[float]:
    import math

    values: list[float] = []
    for index in range(int(seconds * fs)):
        t = index / fs
        beat = math.exp(-(((t % 0.8) - 0.1) ** 2) / 0.0004)
        values.append(0.1 * math.sin(2 * math.pi * 1.2 * t) + beat)
    return values


def _checkpoint(tmp_path, *, classes=("N", "A", "O", "~"), name="test-cnn"):
    """A real ECGNet checkpoint with random weights.

    This validates the loading/scoring pipeline. It is not an accuracy test:
    the weights are untrained, so only the shape and plumbing are asserted.
    """

    torch = pytest.importorskip("torch")
    from app.ml.ecg_cnn import ECGNet

    model = ECGNet(len(classes))
    path = tmp_path / "ecg_model.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "classes": list(classes),
            "fs": 300,
            "win": 9000,
            "name": name,
            "version": "0.1.0",
        },
        path,
    )
    return str(path)


def test_no_model_is_explicitly_unavailable():
    service = MLService(None)

    result = service.predict(_synthetic_ecg(), 200)

    assert service.status.available is False
    assert result.available is False
    assert result.predicted_class is None
    assert result.probabilities is None
    assert "ECG_MODEL_PATH" in result.reason


def test_missing_model_file_is_unavailable(tmp_path):
    service = MLService(str(tmp_path / "does-not-exist.pt"))

    assert service.status.available is False
    assert "not found" in service.status.reason.lower()


def test_a_valid_checkpoint_produces_a_probability_distribution(tmp_path):
    service = MLService(_checkpoint(tmp_path), device="cpu", max_windows=2)

    assert service.status.available is True
    result = service.predict(_synthetic_ecg(), 200)

    assert result.available is True
    assert result.model_name == "test-cnn"
    assert result.model_version == "0.1.0"
    assert result.architecture == "ECGNet-1DCNN"
    assert result.classes == ["N", "A", "O", "~"]
    assert result.predicted_class in result.classes
    assert result.predicted_label
    assert result.probabilities is not None
    assert abs(sum(result.probabilities.values()) - 1.0) < 0.01
    assert result.confidence == result.probabilities[result.predicted_class]
    assert result.window_count >= 1
    assert result.analyzed_at is not None


def test_full_class_names_are_normalised_to_the_short_codes(tmp_path):
    service = MLService(
        _checkpoint(tmp_path, classes=("Normal", "AFib", "Other", "Noisy"))
    )

    result = service.predict(_synthetic_ecg(), 200)

    assert result.available is True
    assert result.classes == ["N", "A", "O", "~"]
    assert result.class_labels["N"] == "Normal rhythm"
    assert set(result.probabilities or {}) == {"N", "A", "O", "~"}


def test_a_checkpoint_without_a_state_dict_is_unavailable(tmp_path):
    torch = pytest.importorskip("torch")
    path = tmp_path / "bad.pt"
    torch.save({"classes": ["N", "A", "O", "~"]}, path)

    service = MLService(str(path))

    assert service.status.available is False
    assert "state_dict" in service.status.reason


def test_a_malformed_json_file_is_unavailable(tmp_path):
    path = tmp_path / "model.json"
    path.write_text(json.dumps({"name": "linear-model"}), encoding="utf-8")

    service = MLService(str(path))

    assert service.status.available is False


def test_empty_samples_are_not_classified(tmp_path):
    service = MLService(_checkpoint(tmp_path))

    result = service.predict([], 200)

    assert result.available is False
    assert "samples" in result.reason.lower()
