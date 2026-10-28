"""The ECG classification interface.

**No model is bundled with this repository.** That is deliberate: shipping a
made-up classifier would turn a demo into a diagnostic claim. The interface is
ready for a validated model; when no model file is configured, ``predict``
returns ``available=False`` with a clear reason and no class or probability.
Nothing here fabricates a prediction.

Model file format (JSON, optional, ``ECG_MODEL_PATH``)::

    {
      "name": "ecg-lr-v1",
      "version": "1.0.0",
      "classes": ["Normal", "AFib", "Other", "Noisy"],
      "feature_names": ["heart_rate_bpm", "rr_std_ms", "rmssd_ms",
                        "pnn50_percent", "quality_score"],
      "mean": [0, 0, 0, 0, 0],
      "scale": [1, 1, 1, 1, 1],
      "coefficients": [[...], [...], [...], [...]],
      "intercept": [0, 0, 0, 0]
    }

``coefficients`` is ``classes x features``; probabilities are produced with a
softmax over the linear scores and are only returned when the model produced
them. A different runtime (ONNX, TorchScript) can replace ``_predict`` without
changing the API response shape.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import ECG_MODEL_PATH

SUPPORTED_CLASSES = ("Normal", "AFib", "Other", "Noisy")


@dataclass
class InferenceStatus:
    available: bool
    reason: str = ""
    model_name: str | None = None
    model_version: str | None = None


@dataclass
class InferenceResult:
    available: bool
    reason: str = ""
    model_name: str | None = None
    model_version: str | None = None
    classes: list[str] = field(default_factory=list)
    predicted_class: str | None = None
    probabilities: dict[str, float] | None = None
    analyzed_at: str | None = None


class InferenceService:
    def __init__(self, path: str | None) -> None:
        self.path = Path(path).expanduser() if path else None
        self._model: dict | None = None
        self._error: str | None = None
        self._load()

    def _load(self) -> None:
        if self.path is None:
            self._error = (
                "No validated ECG classification model is configured on this "
                "deployment (ECG_MODEL_PATH is empty)."
            )
            return
        if not self.path.exists():
            self._error = (
                f"The configured ECG model file was not found at {self.path}."
            )
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self._error = f"The ECG model file could not be read: {exc}."
            return

        required = {"name", "version", "classes", "feature_names", "mean", "scale", "coefficients", "intercept"}
        missing = required - set(payload)
        if missing:
            self._error = (
                "The ECG model file is missing required field(s): "
                + ", ".join(sorted(missing))
                + "."
            )
            return
        if len(payload["classes"]) != len(payload["coefficients"]):
            self._error = "The ECG model has a different number of classes and coefficient rows."
            return
        if any(len(row) != len(payload["feature_names"]) for row in payload["coefficients"]):
            self._error = "The ECG model coefficients do not match its feature list."
            return

        self._model = payload
        self._error = None

    @property
    def status(self) -> InferenceStatus:
        if self._model is None:
            return InferenceStatus(False, self._error or "Inference is unavailable.")
        return InferenceStatus(
            True,
            "",
            self._model.get("name"),
            self._model.get("version"),
        )

    def _features(self, analysis: dict) -> list[float] | None:
        measurements = analysis.get("measurements") or {}
        quality = (analysis.get("signal") or {}).get("quality") or {}
        values = {
            "heart_rate_bpm": measurements.get("heart_rate_bpm"),
            "rr_std_ms": measurements.get("rr_std_ms"),
            "rmssd_ms": measurements.get("rmssd_ms"),
            "pnn50_percent": measurements.get("pnn50_percent"),
            "quality_score": quality.get("score"),
        }
        if not (analysis.get("signal") or {}).get("quality", {}).get("usable"):
            return None
        if values["heart_rate_bpm"] is None:
            return None
        return values

    def _predict(self, features: dict[str, float]) -> InferenceResult:
        assert self._model is not None
        model = self._model
        names = model["feature_names"]
        try:
            vector = [float(features[name]) for name in names]
        except (KeyError, TypeError, ValueError):
            return InferenceResult(
                available=False,
                reason="The deployed model expects features this analysis does not produce.",
                model_name=model.get("name"),
                model_version=model.get("version"),
            )

        normalised = [
            (value - float(mean)) / (float(scale) or 1.0)
            for value, mean, scale in zip(vector, model["mean"], model["scale"])
        ]
        scores = []
        for row, intercept in zip(model["coefficients"], model["intercept"]):
            scores.append(sum(coef * value for coef, value in zip(row, normalised)) + float(intercept))

        # Numerically stable softmax. This is a real probability produced by the
        # deployed model; if the model file is not a classifier, it is not used.
        high = max(scores)
        exps = [math.exp(score - high) for score in scores]
        total = sum(exps)
        probabilities = {
            str(label): round(value / total, 4)
            for label, value in zip(model["classes"], exps)
        }
        predicted = max(probabilities, key=probabilities.get)
        return InferenceResult(
            available=True,
            model_name=model.get("name"),
            model_version=model.get("version"),
            classes=[str(value) for value in model["classes"]],
            predicted_class=predicted,
            probabilities=probabilities,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

    def predict(self, analysis: dict) -> InferenceResult:
        if self._model is None:
            return InferenceResult(available=False, reason=self._error or "Inference is unavailable.")
        features = self._features(analysis)
        if features is None:
            return InferenceResult(
                available=False,
                reason="The signal quality or measurements are insufficient for classification.",
                model_name=self._model.get("name"),
                model_version=self._model.get("version"),
            )
        return self._predict(features)


_singleton: InferenceService | None = None


def get_inference_service() -> InferenceService:
    global _singleton
    if _singleton is None:
        _singleton = InferenceService(ECG_MODEL_PATH)
    return _singleton


def reset_inference_service() -> None:
    """Testing hook: reload the model configuration."""
    global _singleton
    _singleton = None
