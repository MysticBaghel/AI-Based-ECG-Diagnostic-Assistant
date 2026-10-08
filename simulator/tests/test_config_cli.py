"""Configuration and CLI: where the token comes from, and which values are refused.

The precedence rule is the one to get right, and it is tested here rather than
in a smoke run because the failure mode - "the simulator uploaded to the wrong
session" - is silent.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from simulator.cli import build_config, build_parser, validate
from simulator.config import (
    ENV_PREFIX,
    Config,
    ConfigError,
    config_from_env,
    parse_mint_file,
    resolve_session_values,
)

MINT_CONTENT = """\
# written by scripts/mint_run.py
DEVICE_TOKEN=device.jwt.value
SESSION_ID=11111111-1111-4111-8111-111111111111
USER_TOKEN=user.jwt.value
PATIENT_ID=14
DEVICE_ID=22222222-2222-4222-8222-222222222222
"""


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    """No test should inherit an `ECG_SIM_*` variable from the machine it runs on."""
    for name in list(os.environ):
        if name.startswith(ENV_PREFIX):
            monkeypatch.delenv(name, raising=False)
    yield


# --- the mint file --------------------------------------------------------


def test_mint_file_is_parsed_as_key_value(workdir: Path) -> None:
    path = workdir / "mint.txt"
    path.write_text(MINT_CONTENT, encoding="utf-8")

    values = parse_mint_file(path)
    assert values["DEVICE_TOKEN"] == "device.jwt.value"
    assert values["SESSION_ID"].startswith("1111")
    assert values["DEVICE_ID"] == "22222222-2222-4222-8222-222222222222"


def test_a_missing_mint_file_is_not_an_error(workdir: Path) -> None:
    assert parse_mint_file(workdir / "nope.txt") == {}


def test_mint_values_fill_the_gaps(workdir: Path) -> None:
    path = workdir / "mint.txt"
    path.write_text(MINT_CONTENT, encoding="utf-8")

    values, sources = resolve_session_values(
        device_token=None, session_id=None, mint_file=path
    )
    assert values["device_token"] == "device.jwt.value"
    assert values["session_id"].startswith("1111")
    assert sources["device_token"] == "mint.txt"


def test_an_explicit_argument_beats_the_mint_file(workdir: Path, monkeypatch) -> None:
    path = workdir / "mint.txt"
    path.write_text(MINT_CONTENT, encoding="utf-8")
    monkeypatch.setenv(ENV_PREFIX + "DEVICE_TOKEN", "from.env")

    values, sources = resolve_session_values(
        device_token="from.argument", session_id=None, mint_file=path
    )
    assert values["device_token"] == "from.argument"
    assert sources["device_token"] == "argument"
    # The session still comes from the file.
    assert values["session_id"].startswith("1111")


def test_the_environment_beats_the_mint_file(workdir: Path, monkeypatch) -> None:
    path = workdir / "mint.txt"
    path.write_text(MINT_CONTENT, encoding="utf-8")
    monkeypatch.setenv(ENV_PREFIX + "DEVICE_TOKEN", "from.env")

    values, sources = resolve_session_values(device_token=None, session_id=None, mint_file=path)
    assert values["device_token"] == "from.env"
    assert sources["device_token"] == "environment"


# --- the environment ------------------------------------------------------


def test_environment_variables_are_read_with_types(monkeypatch) -> None:
    monkeypatch.setenv(ENV_PREFIX + "DURATION_SECONDS", "12.5")
    monkeypatch.setenv(ENV_PREFIX + "INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv(ENV_PREFIX + "ECG", "true")
    monkeypatch.setenv(ENV_PREFIX + "NOISE", "1")
    monkeypatch.setenv(ENV_PREFIX + "DROP_CHUNKS", "0.25")
    monkeypatch.setenv(ENV_PREFIX + "MAX_ATTEMPTS", "5")

    config = config_from_env()
    assert config.duration_seconds == 12.5
    assert config.interval_seconds == 0.5
    assert config.ecg is True
    assert config.noise is True
    assert config.drop_chunks == 0.25
    assert config.max_attempts == 5


def test_a_command_line_value_beats_the_environment(monkeypatch) -> None:
    monkeypatch.setenv(ENV_PREFIX + "DURATION_SECONDS", "99")
    config = config_from_env(duration_seconds=5.0)
    assert config.duration_seconds == 5.0


def test_an_override_of_none_keeps_the_environment_value(monkeypatch) -> None:
    """`None` means "not passed on the command line", not "set it to nothing"."""
    monkeypatch.setenv(ENV_PREFIX + "DURATION_SECONDS", "99")
    config = config_from_env(duration_seconds=None)
    assert config.duration_seconds == 99.0


# --- the CLI --------------------------------------------------------------


def test_the_parser_accepts_the_documented_flags() -> None:
    args = build_parser().parse_args(
        [
            "--base-url", "http://127.0.0.1:9999",
            "--device-token", "t",
            "--session-id", "s",
            "--duration", "30",
            "--interval", "1",
            "--ecg",
            "--noise",
            "--drop-chunks", "0.1",
            "--resend-chunks", "0.2",
            "--offline-after", "10",
            "--ecg-chunk-seconds", "2",
            "--output-json", "out.json",
        ]
    )
    assert args.base_url == "http://127.0.0.1:9999"
    assert args.ecg is True
    assert args.noise is True
    assert args.drop_chunks == 0.1
    assert args.offline_after == 10


def test_build_config_reads_the_mint_file(workdir: Path) -> None:
    path = workdir / "mint.txt"
    path.write_text(MINT_CONTENT, encoding="utf-8")
    args = build_parser().parse_args(["--mint-file", str(path)])

    config = build_config(args, argv_provided=set())
    assert config.device_token == "device.jwt.value"
    assert config.session_id.startswith("1111")
    assert config.sources["device_token"] == "mint.txt"


def test_offline_after_shortens_the_run() -> None:
    assert Config(duration_seconds=30, offline_after_seconds=10).effective_duration() == 10
    assert Config(duration_seconds=30, offline_after_seconds=60).effective_duration() == 30
    assert Config(duration_seconds=30).effective_duration() == 30


# --- validation -----------------------------------------------------------


def _valid(**overrides) -> Config:
    base = dict(
        device_token="token",
        session_id="11111111-1111-4111-8111-111111111111",
        duration_seconds=5.0,
        interval_seconds=1.0,
    )
    base.update(overrides)
    return Config(**base)


def test_a_valid_configuration_passes() -> None:
    validate(_valid())


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"device_token": None}, "device-token"),
        ({"session_id": None}, "session-id"),
        ({"duration_seconds": 0}, "duration"),
        ({"interval_seconds": -1}, "interval"),
        ({"drop_chunks": 1.5}, "drop-chunks"),
        ({"resend_chunks": -0.1}, "resend-chunks"),
        ({"offline_after_seconds": -5}, "offline-after"),
        ({"max_attempts": 0}, "max-attempts"),
        ({"ecg": True, "ecg_chunk_seconds": 9.0}, "ecg-chunk-seconds"),
        ({"ecg": True, "ecg_chunk_seconds": 0.5}, "ecg-chunk-seconds"),
    ],
)
def test_an_impossible_configuration_is_refused(overrides: dict, expected: str) -> None:
    with pytest.raises(ConfigError) as excinfo:
        validate(_valid(**overrides))
    assert expected in str(excinfo.value)


def test_ecg_chunk_length_is_only_checked_when_ecg_is_on() -> None:
    """`--ecg-chunk-seconds 9` with no `--ecg` cannot hurt anything; allow it."""
    validate(_valid(ecg=False, ecg_chunk_seconds=9.0))
