"""The advisory packaging, template cases and the API-ready provider."""

from app.ai.advisory import (
    DISCLAIMER,
    RemoteAdvisor,
    build_request,
    get_advisor,
)
from app.ai.prompt import PROMPT_VERSION, SYSTEM_PROMPT


def _analysis(*, code="N", available=True, usable=True, simulation=None):
    labels = {
        "N": "Normal rhythm",
        "A": "Atrial fibrillation pattern",
        "O": "Other rhythm",
        "~": "Noisy / unreadable",
    }
    return {
        "session_id": "33333333-3333-4333-8333-333333333333",
        "signal": {
            "sample_rate_hz": 200,
            "sample_count": 1200,
            "duration_seconds": 6.0,
            "chunks": 1,
            "quality": {
                "score": 86.0,
                "level": "good",
                "usable": usable,
                "reasons": [] if usable else ["Signal is flat."],
            },
        },
        "measurements": {
            "heart_rate_bpm": 72.0,
            "rr_mean_ms": 833.0,
            "rr_std_ms": 18.0,
            "rmssd_ms": 22.0,
            "pnn50_percent": 6.0,
            "beats_detected": 7,
        },
        "ml": {
            "available": available,
            "reason": "" if available else "No trained ECG model is configured.",
            "model_name": "test-cnn",
            "model_version": "0.1.0",
            "architecture": "ECGNet-1DCNN",
            "predicted_class": code if available else None,
            "predicted_label": labels.get(code) if available else None,
            "confidence": 0.72 if available else None,
            "probabilities": (
                {"N": 0.72, "A": 0.1, "O": 0.1, "~": 0.08} if available else None
            ),
            "class_labels": labels,
            "window_count": 1,
            "window_seconds": 30.0,
        },
        "findings": ["Measured heart rate: 72 bpm."],
        "limitations": ["Screening aid only."],
        "simulation": simulation,
    }


def test_build_request_packages_measurements_and_excludes_raw_samples():
    request = build_request(_analysis(code="A"))

    assert request["schema_version"] == "ecg-advisor-input/v1"
    assert request["prompt_version"] == PROMPT_VERSION
    assert request["recording"]["session_id"].startswith("3333")
    assert request["recording"]["quality"]["usable"] is True
    assert request["measurements"]["heart_rate_bpm"] == 72.0
    assert request["classification"]["predicted_class"] == "A"
    assert request["classification"]["confidence"] == 0.72
    assert "samples" not in request
    assert "waveform_samples" not in request
    assert request["safety"]["not_a_diagnosis"] is True


def test_demonstration_provenance_is_carried_into_the_request():
    request = build_request(
        _analysis(
            simulation={"kind": "scenario", "scenario": "afib", "label": "AFib"}
        )
    )

    assert request["recording"]["is_demonstration"] is True
    assert request["recording"]["demonstration"]["label"] == "AFib"


def test_the_template_advisor_has_a_cautious_case_for_every_class():
    advisor = get_advisor()
    assert advisor.provider == "template"

    expected_risk = {"N": "low", "A": "moderate", "O": "moderate", "~": "unknown"}
    for code in ("N", "A", "O", "~"):
        advice = advisor.advise(build_request(_analysis(code=code)))

        assert advice["available"] is True
        assert advice["case"] == code
        assert advice["risk_level"] == expected_risk[code]
        assert advice["headline"]
        assert advice["summary"]
        assert advice["recommendations"]
        assert advice["disclaimer"] == DISCLAIMER
        assert advice["provider"] == "template"
        assert advice["prompt_version"] == PROMPT_VERSION
        assert advice["input"]["classification"]["predicted_class"] == code


def test_missing_classification_produces_advice_not_a_guess():
    advisor = get_advisor()
    advice = advisor.advise(build_request(_analysis(available=False)))

    assert advice["available"] is True
    assert advice["case"] == "unavailable"
    assert advice["risk_level"] == "unknown"
    assert "No machine-learning class" in advice["summary"]
    assert "repeat" in " ".join(advice["recommendations"]).lower()


def test_unusable_signal_produces_a_repeat_recording_advice():
    advisor = get_advisor()
    advice = advisor.advise(build_request(_analysis(usable=False)))

    assert advice["case"] == "unusable_signal"
    assert advice["risk_level"] == "unknown"
    assert "usable" in advice["summary"].lower()
    assert any("repeat" in item.lower() for item in advice["recommendations"])


def test_the_system_prompt_is_a_versioned_safety_contract():
    assert PROMPT_VERSION == "ecg-advisor-v1"
    assert "not a licensed clinician" in SYSTEM_PROMPT
    assert "Never write a definitive diagnosis" in SYSTEM_PROMPT
    assert "medication" in SYSTEM_PROMPT
    assert "risk_level" in SYSTEM_PROMPT
    assert "red_flags" in SYSTEM_PROMPT


def test_remote_advisor_without_a_url_is_explicitly_unavailable():
    advisor = RemoteAdvisor(url=None, api_key=None, model=None)

    assert advisor.available is False
    assert "AI_ADVISOR_API_URL" in advisor.reason

    advice = advisor.advise(build_request(_analysis()))

    assert advice["available"] is False
    assert advice["provider"] == "api"
    assert advice["case"] == "unavailable"
    assert "not configured" in advice["reason"]


def test_remote_advisor_parses_an_openai_envelope(monkeypatch):
    advisor = RemoteAdvisor(
        url="https://example.invalid/v1/chat/completions",
        api_key="secret",
        model="test-model",
    )
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        "```json\n"
                        '{"risk_level":"moderate","headline":"Review advised",'
                        '"summary":"A cautious summary.","recommendations":["Review the ECG."],'
                        '"red_flags":["Chest pain."],"confidence_note":"Model confidence is moderate."}'
                        "\n```"
                    )
                }
            }
        ]
    }
    monkeypatch.setattr(advisor, "_post", lambda messages: response)

    advice = advisor.advise(build_request(_analysis(code="A")))

    assert advice["available"] is True
    assert advice["provider"] == "api"
    assert advice["provider_model"] == "test-model"
    assert advice["risk_level"] == "moderate"
    assert advice["headline"] == "Review advised"
    assert advice["recommendations"] == ["Review the ECG."]
    assert advice["red_flags"] == ["Chest pain."]


def test_remote_advisor_turns_a_bad_response_into_unavailable(monkeypatch):
    advisor = RemoteAdvisor(
        url="https://example.invalid/v1/chat/completions",
        api_key=None,
        model=None,
    )
    monkeypatch.setattr(advisor, "_post", lambda messages: {"choices": []})

    advice = advisor.advise(build_request(_analysis()))

    assert advice["available"] is False
    assert advice["provider"] == "api"
    assert "could not" in advice["reason"].lower()


def test_switching_to_the_api_provider_without_a_url_is_safe(monkeypatch):
    import app.ai.advisory as module

    monkeypatch.setattr(module, "AI_ADVISOR_PROVIDER", "api")
    monkeypatch.setattr(module, "AI_ADVISOR_API_URL", None)
    monkeypatch.setattr(module, "AI_ADVISOR_API_KEY", None)
    monkeypatch.setattr(module, "AI_ADVISOR_MODEL", None)
    module.reset_advisor()

    try:
        advisor = module.get_advisor()
        assert advisor.provider == "api"
        assert advisor.available is False

        advice = advisor.advise(build_request(_analysis()))
        assert advice["available"] is False
        assert advice["provider"] == "api"
    finally:
        module.reset_advisor()
