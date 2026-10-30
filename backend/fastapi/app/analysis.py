"""Analysis orchestration: DSP measurements, CNN classification and AI advice.

The pipeline is deliberately staged so each part can fail independently:

1. deterministic DSP always runs and produces measurements + a quality score;
2. the 1-D CNN runs only when the signal is usable and a checkpoint is loaded;
3. the advisory layer packages the result and asks the configured provider
   (a deterministic template today, an AI API later);
4. every stage's outcome - including "unavailable" and why - is stored.

No stage fabricates the output of a later stage.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from app.ai.advisory import advise, build_request, unavailable_advice
from app.core.config import MIN_ANALYSIS_SECONDS, MIN_SIGNAL_QUALITY
from app.dsp import analyse_chunks, extract_signal
from app.inference import MLService, get_inference_service

LIMITATIONS = [
    "Single-lead ECG: rhythm and morphology assessment is limited compared with a clinical ECG.",
    "Measurements are withheld when signal quality is insufficient; a heart rate is not invented.",
    "The 4-class 1-D CNN (N / A / O / ~) is an experimental screening classifier. It was trained on 30-second single-lead windows and has not been validated for clinical use in this deployment.",
    "The AI advisory is generated from these measurements and the classifier output. It is a screening aid, not a diagnosis, and needs clinical interpretation.",
    "A qualified clinician must interpret the recording in the clinical context.",
]


def _findings(result: dict) -> list[str]:
    quality = result["signal"]["quality"]
    measurements = result["measurements"]
    ml = result.get("ml") or {}
    advice = result.get("advice") or {}
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
            "and automated classification are not reported for this recording."
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

    if ml.get("available") and ml.get("predicted_class"):
        probability = ml.get("confidence")
        if probability is None:
            probability = (ml.get("probabilities") or {}).get(ml["predicted_class"])
        suffix = (
            f" (model confidence {float(probability) * 100:.1f}%)"
            if probability is not None
            else ""
        )
        label = ml.get("predicted_label") or ml["predicted_class"]
        findings.append(
            f"Experimental 1-D CNN classification: {ml['predicted_class']} "
            f"({label}){suffix}. This is a screening signal, not a diagnosis."
        )
    else:
        findings.append(
            "ECG classification is unavailable for this recording; no class or "
            "probability has been fabricated."
        )

    if advice.get("available") and advice.get("headline"):
        findings.append(
            f"AI advisory ({advice.get('provider', 'unknown')}): "
            f"{advice['headline']}."
        )
    elif advice:
        findings.append(
            "AI advice is unavailable for this recording; the stored analysis "
            "still contains the signal measurements and any classifier output."
        )

    return findings


def _ml_unavailable(service: MLService, reason: str):
    return service.unavailable(reason)


def run_analysis(
    session_id: str,
    chunks: list[dict],
    *,
    simulation: dict | None = None,
    include_ml: bool = True,
    include_advice: bool = True,
) -> dict:
    """Run the full pipeline and return the payload stored in the database.

    ``include_ml`` and ``include_advice`` exist for the live monitor: recomputing
    a CNN and an advisory on every 4-second poll would be wasteful and could
    overload an external AI API. The stored analysis always runs both.
    """
    result = analyse_chunks(
        chunks,
        min_quality=MIN_SIGNAL_QUALITY,
        min_seconds=MIN_ANALYSIS_SECONDS,
    )
    if simulation is not None:
        result["simulation"] = simulation
    result["session_id"] = session_id

    service = get_inference_service()
    quality = result["signal"]["quality"]
    raw_samples, sample_rate = extract_signal(chunks)

    if not include_ml:
        ml = _ml_unavailable(
            service,
            "The live preview reports deterministic DSP measurements only; the "
            "classifier runs when the recording is analysed.",
        )
    elif not quality.get("usable"):
        ml = _ml_unavailable(
            service,
            "The signal did not meet the quality threshold, so it was not classified.",
        )
    elif not raw_samples or not sample_rate:
        ml = _ml_unavailable(
            service,
            "The stored chunks do not supply one complete signal at a single sample rate.",
        )
    else:
        ml = service.predict(raw_samples, sample_rate)

    result["ml"] = asdict(ml)

    # The advisory input includes the findings that exist before advice. Build
    # them once, ask the advisor, then rebuild so the stored findings also
    # mention the advisory.
    result["findings"] = _findings(result)
    if include_advice:
        result["advice"] = advise(result)
    else:
        result["advice"] = unavailable_advice(
            "disabled",
            "The AI advisory is not run for the live preview; run the stored "
            "analysis to generate it.",
            build_request(result),
        )

    result["findings"] = _findings(result)
    result["limitations"] = list(LIMITATIONS)
    result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
    return result
