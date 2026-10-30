"""ECG classification service.

The 1-D CNN itself lives in :mod:`app.ml.ecg_cnn`; this module owns the model
lifecycle, the API-facing result shape and the honest "unavailable" path.

There is no bundled model. ``ECG_MODEL_PATH`` must point at the ``ecg_model.pt``
produced by ``ml/ecg_train.ipynb`` (or an equivalent checkpoint of the same
architecture). When it is missing, PyTorch is not installed, or the checkpoint
is malformed, every caller receives ``available=False`` with a concrete reason
and no class or probability. Nothing here fabricates a prediction.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import (
    ECG_MAX_WINDOWS,
    ECG_MODEL_DEVICE,
    ECG_MODEL_PATH,
    ROOT_DIR,
)
from app.ml.taxonomy import (
    CLASS_ORDER,
    info_for,
    labels_for,
    normalise_code,
    order_for,
)

logger = logging.getLogger(__name__)

ARCHITECTURE = "ECGNet-1DCNN"


@dataclass
class MLStatus:
    """What the deployment can currently do, for `/health` and the dashboard."""

    available: bool
    reason: str = ""
    model_name: str | None = None
    model_version: str | None = None
    model_sha256: str | None = None
    device: str | None = None
    architecture: str = ARCHITECTURE
    torch_available: bool = False


@dataclass
class MLResult:
    """One model classification, ready to be stored or packaged for an advisor."""

    available: bool
    reason: str = ""
    model_name: str | None = None
    model_version: str | None = None
    model_sha256: str | None = None
    architecture: str = ARCHITECTURE
    device: str | None = None
    classes: list[str] = field(default_factory=list)
    class_labels: dict[str, str] = field(default_factory=dict)
    predicted_class: str | None = None
    predicted_label: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    window_count: int = 0
    window_seconds: float = 0.0
    signal_duration_seconds: float = 0.0
    analyzed_at: str | None = None


# Backwards-compatible names: the rest of the codebase used "inference" before
# the model became a real CNN. Keeping the aliases avoids a churn-only rename.
InferenceStatus = MLStatus
InferenceResult = MLResult


def _runtime_available() -> tuple[bool, str]:
    """Check for the optional ML extras without importing them."""

    for module in ("torch", "numpy", "scipy"):
        try:
            spec = importlib.util.find_spec(module)
        except (ImportError, ValueError):
            spec = None
        if spec is None:
            return False, (
                f"The {module} package is not installed, so the ECG classifier "
                "cannot run. Install backend/fastapi/requirements-ml.txt."
            )
    return True, ""


def _resolve_model_path(path: str) -> Path:
    """Resolve a relative checkpoint path against cwd, then the repository root.

    The documented run command starts uvicorn from ``backend/fastapi``, while
    the training notebook writes ``ml/ecg_model.pt`` at the repository root.
    Trying both makes ``ECG_MODEL_PATH=ml/ecg_model.pt`` work in either place
    instead of failing with a confusing "file not found".
    """

    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    from_cwd = Path.cwd() / candidate
    if from_cwd.exists():
        return from_cwd
    from_root = ROOT_DIR / candidate
    if from_root.exists():
        return from_root
    return from_cwd


class MLService:
    """Load one checkpoint and score raw ECG arrays with it."""

    def __init__(
        self,
        path: str | None,
        *,
        device: str = "cpu",
        max_windows: int = 8,
    ) -> None:
        self.path = _resolve_model_path(path) if path else None
        self.requested_device = device
        self.max_windows = max(1, int(max_windows))
        self._model = None
        self._meta: dict | None = None
        self._error: str | None = None
        self._torch_available = False
        self._load()

    # -- lifecycle ---------------------------------------------------------

    def _load(self) -> None:
        self._torch_available = importlib.util.find_spec("torch") is not None
        if self.path is None:
            self._error = (
                "No trained ECG model is configured on this deployment "
                "(ECG_MODEL_PATH is empty). Export ecg_model.pt from "
                "ml/ecg_train.ipynb and point ECG_MODEL_PATH at it."
            )
            return
        if not self.path.exists():
            self._error = f"The configured ECG model file was not found at {self.path}."
            return

        runtime_ok, runtime_message = _runtime_available()
        if not runtime_ok:
            self._error = runtime_message
            return

        try:
            from app.ml import ecg_cnn
        except Exception as exc:  # noqa: BLE001 - optional runtime, keep serving
            self._error = f"The ECG model runtime could not be imported: {exc}"
            return

        try:
            model, meta = ecg_cnn.load_checkpoint(self.path, self.requested_device)
        except Exception as exc:  # noqa: BLE001 - a bad file must not crash the API
            self._error = f"The ECG model file could not be loaded: {exc}"
            return

        self._model = model
        self._meta = meta
        self._error = None

    @property
    def status(self) -> MLStatus:
        if self._model is None or self._meta is None:
            return MLStatus(
                available=False,
                reason=self._error or "The ECG classifier is unavailable.",
                torch_available=self._torch_available,
            )
        return MLStatus(
            available=True,
            model_name=self._meta.get("name"),
            model_version=self._meta.get("version"),
            model_sha256=self._meta.get("sha256"),
            device=self._meta.get("device"),
            architecture=self._meta.get("architecture", ARCHITECTURE),
            torch_available=self._torch_available,
        )

    # -- prediction --------------------------------------------------------

    def _unavailable(self, reason: str) -> MLResult:
        return MLResult(
            available=False,
            reason=reason,
            model_name=(self._meta or {}).get("name"),
            model_version=(self._meta or {}).get("version"),
            model_sha256=(self._meta or {}).get("sha256"),
            architecture=(self._meta or {}).get("architecture", ARCHITECTURE),
            device=(self._meta or {}).get("device"),
        )

    def unavailable(self, reason: str) -> MLResult:
        """A public "cannot classify" result for the orchestration layer."""

        return self._unavailable(reason)

    def predict(self, samples, sample_rate_hz: int) -> MLResult:
        """Classify a raw ECG trace.

        ``samples`` is the unfiltered signal the device sent. Preprocessing
        (resampling, band-pass, z-score) happens inside the ML runtime, exactly
        as it did in training.
        """

        if self._model is None or self._meta is None:
            return self._unavailable(self._error or "The ECG classifier is unavailable.")
        if not samples:
            return self._unavailable("No ECG samples were available for classification.")
        if not sample_rate_hz or int(sample_rate_hz) <= 0:
            return self._unavailable("The ECG sample rate is unknown, so the trace cannot be scored.")

        from app.ml import ecg_cnn

        try:
            raw = ecg_cnn.predict(
                self._model,
                samples,
                fs=int(sample_rate_hz),
                device=self._meta.get("device", "cpu"),
                max_windows=self.max_windows,
            )
        except Exception as exc:  # noqa: BLE001 - classify failure as unavailable
            logger.warning("ECG classification failed: %s", exc)
            return self._unavailable(
                f"The classifier could not score this recording: {str(exc)[:300]}"
            )

        model_codes = [normalise_code(code) for code in self._meta.get("classes", CLASS_ORDER)]
        values = raw["probabilities"]
        by_code = {
            code: round(float(value), 4) for code, value in zip(model_codes, values)
        }
        predicted_code = model_codes[int(raw["predicted_index"])]
        classes = order_for(model_codes)
        # Probabilities are keyed by the canonical code; a checkpoint with a
        # duplicate alias would otherwise silently lose a row.
        probabilities = {code: by_code[code] for code in classes}
        confidence = max(probabilities.values()) if probabilities else None
        predicted_label = info_for(predicted_code).label

        return MLResult(
            available=True,
            model_name=self._meta.get("name"),
            model_version=self._meta.get("version"),
            model_sha256=self._meta.get("sha256"),
            architecture=self._meta.get("architecture", ARCHITECTURE),
            device=self._meta.get("device"),
            classes=classes,
            class_labels=labels_for(classes),
            predicted_class=predicted_code,
            predicted_label=predicted_label,
            confidence=confidence,
            probabilities=probabilities,
            window_count=int(raw.get("window_count", 0)),
            window_seconds=round(float(raw.get("window_seconds", 0.0)), 3),
            signal_duration_seconds=round(float(raw.get("signal_seconds", 0.0)), 3),
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )


_singleton: MLService | None = None


def get_inference_service() -> MLService:
    """The process-wide classifier, loaded once from configuration."""

    global _singleton
    if _singleton is None:
        _singleton = MLService(
            ECG_MODEL_PATH,
            device=ECG_MODEL_DEVICE,
            max_windows=ECG_MAX_WINDOWS,
        )
    return _singleton


def reset_inference_service() -> None:
    """Testing hook: reload the model configuration."""

    global _singleton
    _singleton = None


__all__ = [
    "ARCHITECTURE",
    "InferenceResult",
    "InferenceStatus",
    "MLResult",
    "MLService",
    "MLStatus",
    "get_inference_service",
    "reset_inference_service",
]
