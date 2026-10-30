"""AI advisory pipeline: package the analysis, then ask a provider for advice.

Two providers exist today:

* ``template`` - deterministic, hard-coded advice for each classifier case. It
  is a placeholder for the future AI API and is what the UI shows now.
* ``api`` - an OpenAI-compatible chat-completions call. It is disabled until
  ``AI_ADVISOR_API_URL`` (and usually ``AI_ADVISOR_API_KEY``) is set.

Both return the same :class:`dict` shape, which is stored beside the analysis.
The packaged request is stored too, so the exact input can be replayed or sent to
a different provider later without re-running DSP or the CNN.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.ai.prompt import INPUT_SCHEMA_VERSION, PROMPT_VERSION, build_messages
from app.core.config import (
    AI_ADVISOR_API_KEY,
    AI_ADVISOR_API_URL,
    AI_ADVISOR_MODEL,
    AI_ADVISOR_PROVIDER,
    AI_ADVISOR_TIMEOUT_SECONDS,
)
from app.ml.taxonomy import info_for

logger = logging.getLogger(__name__)

RISK_LEVELS = {"low", "moderate", "high", "unknown"}

DISCLAIMER = (
    "Automated screening aid, not a medical diagnosis. A qualified clinician must "
    "interpret the recording in the patient's clinical context."
)

#: Red flags shared by every case. The template provider never claims these are
#: present; it tells the reader what would warrant urgent assessment.
COMMON_RED_FLAGS = [
    "Chest pain, pressure or tightness.",
    "Fainting or near-fainting.",
    "Severe or sudden shortness of breath.",
    "Palpitations with dizziness, sweating or collapse.",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any, digits: int = 1) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _measurement_sentence(request: dict) -> str:
    measurements = request.get("measurements") or {}
    quality = (request.get("recording") or {}).get("quality") or {}
    parts: list[str] = []
    heart_rate = _number(measurements.get("heart_rate_bpm"), 0)
    if heart_rate is not None:
        parts.append(f"Measured heart rate was about {heart_rate:.0f} bpm.")
    score = _number(quality.get("score"), 0)
    if score is not None:
        parts.append(
            f"Signal quality was {quality.get('level', 'unknown')} ({score:.0f}/100)."
        )
    return " ".join(parts)


def _provenance_sentence(request: dict) -> str:
    recording = request.get("recording") or {}
    if not recording.get("is_demonstration"):
        return ""
    demonstration = recording.get("demonstration") or {}
    label = demonstration.get("label") or demonstration.get("scenario") or "simulated"
    return (
        f"This recording is demonstration data from the built-in simulator "
        f"({label}); it is not a patient recording."
    )


def build_request(analysis: dict) -> dict:
    """Package one completed analysis into the advisor input contract.

    Raw waveform samples are deliberately excluded: the advisor needs the
    measurements and the classifier summary, not a multi-megabyte trace. The
    payload is JSON-serialisable and contains no direct patient identifiers.
    """

    signal = analysis.get("signal") or {}
    quality = signal.get("quality") or {}
    measurements = analysis.get("measurements") or {}
    ml = analysis.get("ml") or analysis.get("ai") or {}
    simulation = analysis.get("simulation")

    recording = {
        "session_id": analysis.get("session_id"),
        "duration_seconds": _number(signal.get("duration_seconds"), 3),
        "sample_rate_hz": signal.get("sample_rate_hz"),
        "chunks": signal.get("chunks", 0),
        "quality": {
            "score": quality.get("score"),
            "level": quality.get("level", "unknown"),
            "usable": bool(quality.get("usable")),
            "reasons": list(quality.get("reasons") or []),
        },
        "is_demonstration": simulation is not None,
        "demonstration": (
            {
                "kind": simulation.get("kind"),
                "scenario": simulation.get("scenario"),
                "label": simulation.get("label"),
            }
            if simulation
            else None
        ),
    }

    classification = {
        "available": bool(ml.get("available")),
        "reason": ml.get("reason") or "",
        "model": {
            "name": ml.get("model_name"),
            "version": ml.get("model_version"),
            "architecture": ml.get("architecture"),
        },
        "predicted_class": ml.get("predicted_class"),
        "predicted_label": ml.get("predicted_label")
        or (info_for(ml.get("predicted_class")).label if ml.get("predicted_class") else None),
        "confidence": _number(ml.get("confidence"), 4),
        "probabilities": dict(ml.get("probabilities") or {}),
        "class_labels": dict(ml.get("class_labels") or {}),
        "window_count": ml.get("window_count", 0),
        "window_seconds": ml.get("window_seconds", 0),
    }

    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "generated_at": _now(),
        "recording": recording,
        "measurements": {
            "heart_rate_bpm": _number(measurements.get("heart_rate_bpm")),
            "rr_mean_ms": _number(measurements.get("rr_mean_ms")),
            "rr_std_ms": _number(measurements.get("rr_std_ms")),
            "rmssd_ms": _number(measurements.get("rmssd_ms")),
            "pnn50_percent": _number(measurements.get("pnn50_percent")),
            "beats_detected": measurements.get("beats_detected", 0),
        },
        "classification": classification,
        "findings": list(analysis.get("findings") or []),
        "limitations": list(analysis.get("limitations") or []),
        "safety": {"not_a_diagnosis": True, "single_lead": True},
    }


def unavailable_advice(provider: str, reason: str, request: dict | None = None) -> dict:
    return {
        "available": False,
        "reason": reason,
        "provider": provider,
        "provider_model": None,
        "prompt_version": PROMPT_VERSION,
        "generated_at": _now(),
        "case": "unavailable",
        "risk_level": "unknown",
        "headline": "AI advice unavailable",
        "summary": reason,
        "recommendations": [],
        "red_flags": [],
        "confidence_note": "",
        "disclaimer": DISCLAIMER,
        "input": request or {},
    }


def _classified_case(request: dict) -> str:
    recording = request.get("recording") or {}
    quality = recording.get("quality") or {}
    classification = request.get("classification") or {}
    if not quality.get("usable"):
        return "unusable_signal"
    if not classification.get("available"):
        return "unavailable"
    code = str(classification.get("predicted_class") or "").strip()
    if code in {"N", "A", "O", "~"}:
        return code
    return "unknown"


class TemplateAdvisor:
    """Deterministic placeholder advice, one profile per classifier case.

    This is intentionally not an LLM. It makes the UI and the storage pipeline
    complete and reviewable before an external AI API is connected, and it
    cannot hallucinate a fact that is not in the packaged request.
    """

    provider = "template"

    @property
    def available(self) -> bool:
        return True

    @property
    def reason(self) -> str:
        return ""

    def advise(self, request: dict) -> dict:
        case = _classified_case(request)
        evidence = _measurement_sentence(request)
        provenance = _provenance_sentence(request)
        summary_prefix = (provenance + " ") if provenance else ""

        if case == "N":
            profile = {
                "risk_level": "low",
                "headline": "Normal rhythm pattern suggested",
                "summary": summary_prefix + (
                    "The experimental classifier found a predominantly normal rhythm "
                    "pattern. " + evidence + " This is a screening signal, not a "
                    "diagnosis; a single-lead recording cannot exclude intermittent "
                    "arrhythmia."
                ),
                "recommendations": [
                    "Correlate this result with the patient's symptoms and clinical history.",
                    "Continue routine monitoring and repeat the recording if symptoms occur.",
                    "Interpret the trace alongside any previous ECG and the patient's medication history.",
                ],
                "red_flags": list(COMMON_RED_FLAGS),
                "confidence_note": (
                    "A normal-pattern classification does not rule out arrhythmia; "
                    "model confidence and signal quality are reported separately."
                ),
            }
        elif case == "A":
            profile = {
                "risk_level": "moderate",
                "headline": "Irregular rhythm pattern flagged (possible atrial fibrillation)",
                "summary": summary_prefix + (
                    "The classifier flagged a pattern associated with atrial "
                    "fibrillation. " + evidence + " This is an experimental screening "
                    "signal. Confirmation requires clinical review and a diagnostic ECG."
                ),
                "recommendations": [
                    "Arrange prompt clinical review and a 12-lead ECG to confirm the rhythm.",
                    "Ask the patient about palpitations, breathlessness, chest discomfort and fainting.",
                    "Do not start, stop or change any medication based on this screening result.",
                ],
                "red_flags": list(COMMON_RED_FLAGS),
                "confidence_note": (
                    "The model's atrial-fibrillation class is a pattern match, not a "
                    "confirmed rhythm diagnosis; signal quality and window count affect confidence."
                ),
            }
        elif case == "O":
            profile = {
                "risk_level": "moderate",
                "headline": "Other rhythm pattern flagged",
                "summary": summary_prefix + (
                    "The classifier found a rhythm pattern outside the normal and "
                    "atrial-fibrillation classes. " + evidence + " This is a broad "
                    "screening category and is not a specific diagnosis."
                ),
                "recommendations": [
                    "Arrange clinical review with a 12-lead ECG for rhythm characterisation.",
                    "Review the recording for noise, ectopy or artefact that could explain the result.",
                    "Repeat the recording if the patient is asymptomatic and the trace was poor quality.",
                ],
                "red_flags": list(COMMON_RED_FLAGS),
                "confidence_note": (
                    "The 'other rhythm' class groups several patterns together; it "
                    "should be treated as a prompt for clinical correlation, not a diagnosis."
                ),
            }
        elif case == "~":
            profile = {
                "risk_level": "unknown",
                "headline": "Recording not interpretable",
                "summary": summary_prefix + (
                    "The classifier marked this recording as noisy or unreadable, so "
                    "no reliable rhythm pattern was produced. " + evidence
                ),
                "recommendations": [
                    "Check electrode contact, cable movement and ambient electrical noise.",
                    "Repeat the recording and confirm the trace is stable before interpreting it.",
                    "If the patient has symptoms, arrange clinical assessment regardless of this result.",
                ],
                "red_flags": list(COMMON_RED_FLAGS),
                "confidence_note": (
                    "No clinical conclusion should be drawn from an unreadable recording."
                ),
            }
        elif case == "unusable_signal":
            quality = (request.get("recording") or {}).get("quality") or {}
            reasons = " ".join(str(reason) for reason in (quality.get("reasons") or []))
            profile = {
                "risk_level": "unknown",
                "headline": "Signal quality too low for interpretation",
                "summary": summary_prefix + (
                    "Deterministic signal processing did not consider this recording "
                    "usable, so rhythm measurements and automated classification were "
                    "withheld. " + reasons
                ).strip(),
                "recommendations": [
                    "Repeat the recording after checking electrode placement and cable movement.",
                    "Confirm the device is sampling at a supported rate and is not clipping.",
                    "Assess the patient clinically if there is any concern, independently of this trace.",
                ],
                "red_flags": list(COMMON_RED_FLAGS),
                "confidence_note": (
                    "No measurements or class were produced because the signal did not meet the quality threshold."
                ),
            }
        else:
            reason = (
                (request.get("classification") or {}).get("reason")
                or "No classifier produced a result for this recording."
            )
            profile = {
                "risk_level": "unknown",
                "headline": "Automated classification unavailable",
                "summary": summary_prefix + (
                    "No machine-learning class is available for this recording. " + reason
                ).strip(),
                "recommendations": [
                    "Review the signal-quality reasons and repeat the recording if appropriate.",
                    "Continue with clinical assessment; do not treat the absence of a class as a normal result.",
                ],
                "red_flags": list(COMMON_RED_FLAGS),
                "confidence_note": (
                    "No class or probability has been fabricated for this recording."
                ),
            }

        return {
            "available": True,
            "reason": "",
            "provider": self.provider,
            "provider_model": None,
            "prompt_version": PROMPT_VERSION,
            "generated_at": _now(),
            "case": case,
            "risk_level": profile["risk_level"],
            "headline": profile["headline"],
            "summary": profile["summary"].strip(),
            "recommendations": profile["recommendations"],
            "red_flags": profile["red_flags"],
            "confidence_note": profile["confidence_note"],
            "disclaimer": DISCLAIMER,
            "input": request,
        }


class DisabledAdvisor:
    """The advisor switch is explicitly off."""

    provider = "disabled"

    def __init__(self, reason: str) -> None:
        self._reason = reason

    @property
    def available(self) -> bool:
        return False

    @property
    def reason(self) -> str:
        return self._reason

    def advise(self, request: dict) -> dict:
        return unavailable_advice(self.provider, self._reason, request)


class RemoteAdvisor:
    """OpenAI-compatible chat-completions advisor.

    Configure with::

        AI_ADVISOR_PROVIDER=api
        AI_ADVISOR_API_URL=https://api.example.com/v1/chat/completions
        AI_ADVISOR_API_KEY=...
        AI_ADVISOR_MODEL=...

    The provider is optional. Any network or parsing failure becomes an
    unavailable advisory; the analysis itself is never lost.
    """

    provider = "api"

    def __init__(
        self,
        *,
        url: str | None,
        api_key: str | None,
        model: str | None,
        timeout: float = 30.0,
    ) -> None:
        self.url = (url or "").strip()
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip() or "gpt-4o-mini"
        self.timeout = max(1.0, float(timeout))

    @property
    def available(self) -> bool:
        return bool(self.url)

    @property
    def reason(self) -> str:
        if not self.url:
            return (
                "The remote AI advisor is not configured (AI_ADVISOR_API_URL is empty). "
                "Set AI_ADVISOR_PROVIDER=api with a URL, key and model to enable it."
            )
        return ""

    def _post(self, messages: list[dict]) -> dict:
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0.2,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            self.url, data=body, headers=headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = response.read()
        if not raw:
            raise ValueError("The AI advisor returned an empty response.")
        return json.loads(raw)

    @staticmethod
    def _extract_content(payload: dict) -> dict:
        """Accept an OpenAI envelope or a direct JSON object."""

        if isinstance(payload, dict) and payload.get("risk_level") and payload.get("headline"):
            return payload

        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not choices:
            raise ValueError("The AI advisor response has no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, dict):
            return content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The AI advisor returned no text content.")

        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("The AI advisor response did not contain a JSON object.")
        return json.loads(text[start : end + 1])

    def advise(self, request: dict) -> dict:
        if not self.url:
            return unavailable_advice(self.provider, self.reason, request)

        started = time.monotonic()
        try:
            payload = self._post(build_messages(request))
            data = self._extract_content(payload)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            logger.warning("AI advisor HTTP %s: %s", exc.code, detail)
            return unavailable_advice(
                self.provider,
                f"The AI advisory service answered HTTP {exc.code}.",
                request,
            )
        except (urllib.error.URLError, OSError, ValueError, TypeError) as exc:
            logger.warning("AI advisor failed: %s", exc)
            return unavailable_advice(
                self.provider,
                f"The AI advisory service could not be reached: {str(exc)[:300]}",
                request,
            )

        risk = str(data.get("risk_level") or "unknown").lower()
        if risk not in RISK_LEVELS:
            risk = "unknown"

        def _strings(key: str, limit: int, max_length: int = 500) -> list[str]:
            value = data.get(key)
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list):
                return []
            return [str(item).strip()[:max_length] for item in value if item is not None and str(item).strip()][:limit]

        headline = str(data.get("headline") or "").strip()[:200]
        summary = str(data.get("summary") or "").strip()[:2000]
        if not headline or not summary:
            return unavailable_advice(
                self.provider,
                "The AI advisor returned an incomplete advisory.",
                request,
            )

        return {
            "available": True,
            "reason": "",
            "provider": self.provider,
            "provider_model": self.model,
            "prompt_version": PROMPT_VERSION,
            "generated_at": _now(),
            "case": _classified_case(request),
            "risk_level": risk,
            "headline": headline,
            "summary": summary,
            "recommendations": _strings("recommendations", 5),
            "red_flags": _strings("red_flags", 4),
            "confidence_note": str(data.get("confidence_note") or "").strip()[:500],
            "disclaimer": DISCLAIMER,
            "input": request,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }


_advisor: Any | None = None


def get_advisor() -> TemplateAdvisor | RemoteAdvisor | DisabledAdvisor:
    """The configured advisor, created once per process."""

    global _advisor
    if _advisor is not None:
        return _advisor

    if AI_ADVISOR_PROVIDER == "template":
        _advisor = TemplateAdvisor()
    elif AI_ADVISOR_PROVIDER == "api":
        _advisor = RemoteAdvisor(
            url=AI_ADVISOR_API_URL,
            api_key=AI_ADVISOR_API_KEY,
            model=AI_ADVISOR_MODEL,
            timeout=AI_ADVISOR_TIMEOUT_SECONDS,
        )
    else:
        _advisor = DisabledAdvisor(
            "The AI advisory layer is disabled on this deployment (AI_ADVISOR_PROVIDER=disabled)."
        )
    return _advisor


def reset_advisor() -> None:
    """Testing hook: rebuild the advisor from the current configuration."""

    global _advisor
    _advisor = None


def advise(analysis: dict) -> dict:
    """Package ``analysis`` and run the configured advisor."""

    request = build_request(analysis)
    advisor = get_advisor()
    try:
        return advisor.advise(request)
    except Exception as exc:  # noqa: BLE001 - advice must never break analysis
        logger.exception("Advisor crashed")
        return unavailable_advice(
            getattr(advisor, "provider", "unknown"),
            f"The advisory layer failed: {str(exc)[:300]}",
            request,
        )


__all__ = [
    "DISCLAIMER",
    "DisabledAdvisor",
    "RemoteAdvisor",
    "TemplateAdvisor",
    "advise",
    "build_request",
    "unavailable_advice",
    "get_advisor",
    "reset_advisor",
]
