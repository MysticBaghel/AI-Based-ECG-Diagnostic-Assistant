"""The four-class taxonomy of the ECG classifier.

The training notebook (`ml/ecg_train.ipynb`) predicts the PhysioNet/Computing in
Cardiology Challenge 2017 labels ``N``, ``A``, ``O`` and ``~``. The API exposes
both the short code (stable, model-native) and a human label, so the UI never
has to hard-code a translation.

Nothing in this module imports the ML runtime. It is safe to import when
PyTorch is not installed and when no model file exists.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassInfo:
    """One classifier label, described for humans and for the advisory layer."""

    code: str
    label: str
    description: str
    risk_level: str


#: Ordered exactly as the training notebook defines ``CLASSES``. Keeping this
#: order matters when a checkpoint does not carry its own class list.
CLASS_ORDER: tuple[str, ...] = ("N", "A", "O", "~")

CLASS_INFO: dict[str, ClassInfo] = {
    "N": ClassInfo(
        code="N",
        label="Normal rhythm",
        description="A predominantly normal rhythm pattern.",
        risk_level="low",
    ),
    "A": ClassInfo(
        code="A",
        label="Atrial fibrillation pattern",
        description="A pattern associated with atrial fibrillation.",
        risk_level="moderate",
    ),
    "O": ClassInfo(
        code="O",
        label="Other rhythm",
        description="A rhythm pattern that is neither normal nor atrial fibrillation.",
        risk_level="moderate",
    ),
    "~": ClassInfo(
        code="~",
        label="Noisy / unreadable",
        description="The recording is too noisy or inconsistent for a reliable rhythm classification.",
        risk_level="unknown",
    ),
}

#: Used when a model was trained with a class the taxonomy does not know. The
#: API still reports the model's own code; this only supplies a display label.
UNKNOWN_CLASS = ClassInfo(
    code="?",
    label="Unrecognised class",
    description="The deployed model returned a class outside the documented taxonomy.",
    risk_level="unknown",
)


def normalise_code(value: object) -> str:
    """Return the canonical short code for a model label.

    Checkpoints from the notebook already store ``N/A/O/~``. A model exported by
    another tool may store full words, so the common aliases are accepted
    without inventing a mapping for anything else.
    """

    text = str(value).strip()
    aliases = {
        "n": "N",
        "normal": "N",
        "a": "A",
        "afib": "A",
        "af": "A",
        "atrial fibrillation": "A",
        "o": "O",
        "other": "O",
        "~": "~",
        "noisy": "~",
        "noise": "~",
    }
    return aliases.get(text.lower(), text or "?")


def info_for(code: object) -> ClassInfo:
    """Metadata for a class code, with a safe fallback."""

    normalised = normalise_code(code)
    return CLASS_INFO.get(normalised, UNKNOWN_CLASS)


def labels_for(codes: list[str] | tuple[str, ...]) -> dict[str, str]:
    """``{"N": "Normal rhythm", ...}`` for the classes a checkpoint declares."""

    return {str(code): info_for(code).label for code in codes}


def order_for(codes: list[str] | tuple[str, ...]) -> list[str]:
    """Sort model labels into the canonical order where possible.

    Unknown labels keep their relative order at the end. This makes the API
    deterministic even if a checkpoint lists its classes differently.
    """

    normalised = [normalise_code(code) for code in codes]
    known = [code for code in CLASS_ORDER if code in normalised]
    extra = [code for code in normalised if code not in CLASS_ORDER]
    return known + extra


__all__ = [
    "CLASS_INFO",
    "CLASS_ORDER",
    "ClassInfo",
    "UNKNOWN_CLASS",
    "info_for",
    "labels_for",
    "normalise_code",
    "order_for",
]
