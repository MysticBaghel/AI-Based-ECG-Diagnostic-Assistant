"""Analysis orchestration: DSP measurements plus optional AI inference."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import MIN_ANALYSIS_SECONDS, MIN_SIGNAL_QUALITY
from app.dsp import analyse_chunks
from app.inference import get_inference_service

LIMITATIONS = [
    "Single-lead ECG: rhythm and morphology assessment is limited compared with a clinical ECG.",
    "Measurements are withheld when signal quality is insufficient; a heart rate is not invented.",
    "This analysis is an experimental screening aid, not a diagnosis, and has not been validated for clinical use in this deployment.",
    "A qualified clinician must interpret the recording in the clinical context.",
]


def _findings(result: dict) -> list[str]:
    quality = result["signal"]["quality"]
    measurements = result["measurements"]
    ai = result["ai"]
    findings: list[str] = []

    simulation = result.get("simulation")
    if simulation:
        if simulation.get("kind") == "csv":
            findings.append(
                "Demonstration data: this recording was replayed from the "
                f"uploaded file {simulation.get('label', 'CSV')!r}, not recorded "
                "from a patient."
            )
        else:
            findings.append(
                "Demonstration data: this recording was streamed by the built-in "
                f"simulator ({simulation.get('label', simulation.get('scenario'))} "
                "scenario), not recorded from a patient."
            )

    if not quality["usable"]:
        findings.append(
            "Signal quality did not meet the threshold, so rhythm measurements "
            "are not reported for this recording."
        )
    elif measurements.get("heart_rate_bpm") is not None:
        findings.append(
            f"Measured heart rate: {measurements['heart_rate_bpm']:.0f} bpm from "
            f"{measurements.get('beats_detected', 0)} detected R-peaks."
        )
        findings.append(
            "Heart rate and RR intervals are descriptive signal measurements, "
            "not a rhythm interpretation or diagnosis."
        )

    if ai.get("available") and ai.get("predicted_class"):
        probability = (ai.get("probabilities") or {}).get(ai["predicted_class"])
        suffix = (
            f" (model probability {probability * 100:.1f}%)"
            if probability is not None
            else ""
        )
        findings.append(
            f"Experimental classifier suggestion: {ai['predicted_class']}{suffix}. "
            "This is a screening signal, not a diagnosis."
        )
    else:
        findings.append(
            "AI classification is unavailable for this recording; no prediction "
            "has been fabricated."
        )

    return findings


def run_analysis(
    session_id: str,
    chunks: list[dict],
    *,
    simulation: dict | None = None,
) -> dict:
    """Run DSP and inference and return the payload stored in the database.

    ``simulation`` is provenance, not input: the DSP never sees the scenario
    label. It is copied into the stored payload so the analysis and the report
    can say the recording is demonstration data, and it is what a later
    classifier evaluation can compare a prediction against.
    """
    result = analyse_chunks(
        chunks,
        min_quality=MIN_SIGNAL_QUALITY,
        min_seconds=MIN_ANALYSIS_SECONDS,
    )
    if simulation is not None:
        result["simulation"] = simulation

    service = get_inference_service()
    inference = service.predict(result)
    result["ai"] = {
        "available": inference.available,
        "reason": inference.reason,
        "model_name": inference.model_name,
        "model_version": inference.model_version,
        "classes": inference.classes,
        "predicted_class": inference.predicted_class,
        "probabilities": inference.probabilities,
        "analyzed_at": inference.analyzed_at,
    }
    result["limitations"] = list(LIMITATIONS)
    result["findings"] = _findings(result)
    result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
    return result
