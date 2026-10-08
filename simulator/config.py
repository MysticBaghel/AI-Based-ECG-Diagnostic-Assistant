"""Configuration: where the values come from, and what the defaults are.

Three sources, in this order, each overriding the one after it:

1. a command-line argument            `--device-token abc.def.ghi`
2. an environment variable            `$env:ECG_SIM_DEVICE_TOKEN = "abc.def.ghi"`
3. `.smoke/mint.txt`, written by the Phase 1/2 mint helper

`.smoke/mint.txt` is a `KEY=VALUE` file containing `DEVICE_TOKEN`, `SESSION_ID`,
`USER_TOKEN`, `PATIENT_ID` and `DEVICE_ID`. It exists because a child process'
piped stdout cannot be captured in every environment (see
`docs/phase-2-smoke-test.md`), so the smoke scripts write to a file and every
tool reads from it. The simulator reads the same file, which is what makes
"run the simulator against the session the smoke test just created" a one-liner.

Nothing here is a secret store: a device token is short-lived and the file is
gitignored, and the simulator is a test client, not a service.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

#: `simulator/config.py` -> repository root
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MINT_FILE = REPO_ROOT / ".smoke" / "mint.txt"

DEFAULT_BASE_URL = "http://127.0.0.1:8001"
ENV_PREFIX = "ECG_SIM_"

#: The heartbeat is deliberately slower than the data rate: it exists so the
#: dashboard's "online" indicator stays green, and the threshold is 120 s.
DEFAULT_HEARTBEAT_SECONDS = 10.0
DEFAULT_INTERVAL_SECONDS = 1.0
DEFAULT_DURATION_SECONDS = 30.0
DEFAULT_ECG_CHUNK_SECONDS = 2.0

#: Set by the smoke script so the run can be reproduced exactly.
ENV_SEED = "ECG_SIM_SEED"


class ConfigError(RuntimeError):
    """A configuration the simulator cannot run with, explained in plain words."""


@dataclass
class Config:
    """Everything one simulated run needs."""

    base_url: str = DEFAULT_BASE_URL
    device_token: str | None = None
    session_id: str | None = None
    user_token: str | None = None

    duration_seconds: float = DEFAULT_DURATION_SECONDS
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS
    offline_after_seconds: float | None = None

    # -- ECG ---------------------------------------------------------------
    ecg: bool = False
    ecg_source: str = "auto"
    ecg_record: str = "100"
    ecg_data_dir: str = "simulator/.ecg-data"
    ecg_download: bool = True
    ecg_chunk_seconds: float = DEFAULT_ECG_CHUNK_SECONDS
    ecg_sample_rate_hz: int = 200

    # -- edge cases --------------------------------------------------------
    noise: bool = False
    drop_chunks: float = 0.0
    resend_chunks: float = 0.0

    # -- plumbing ----------------------------------------------------------
    timeout_seconds: float = 10.0
    max_attempts: int = 3
    seed: int | None = None
    output_json: str | None = None
    verbose: bool = False

    #: where each resolved value came from, for the header log line
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def ecg_enabled(self) -> bool:
        return self.ecg

    @property
    def interval(self) -> float:
        return self.interval_seconds

    def effective_duration(self) -> float:
        """How long data is produced: `--offline-after` cuts it short."""
        if self.offline_after_seconds is None:
            return self.duration_seconds
        return min(self.duration_seconds, self.offline_after_seconds)

    def describe(self) -> str:
        """One line describing the run, for the log."""
        parts = [
            f"base_url={self.base_url}",
            f"session_id={self.session_id}",
            f"duration={self.duration_seconds:g}s",
            f"interval={self.interval_seconds:g}s",
            f"heartbeat={self.heartbeat_seconds:g}s",
            f"ecg={'on' if self.ecg else 'off'}",
        ]
        if self.ecg:
            parts.append(f"chunk={self.ecg_chunk_seconds:g}s")
            parts.append(f"source={self.ecg_source}")
        if self.noise:
            parts.append("noise=on")
        if self.drop_chunks:
            parts.append(f"drop={self.drop_chunks:g}")
        if self.resend_chunks:
            parts.append(f"resend={self.resend_chunks:g}")
        if self.offline_after_seconds is not None:
            parts.append(f"offline_after={self.offline_after_seconds:g}s")
        if self.seed is not None:
            parts.append(f"seed={self.seed}")
        return " ".join(parts)


# --- .smoke/mint.txt -------------------------------------------------------


def parse_mint_file(path: Path | str) -> dict[str, str]:
    """Read `KEY=VALUE` lines. Missing file or unreadable lines are fine."""
    values: dict[str, str] = {}
    path = Path(path)
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def resolve_session_values(
    *,
    device_token: str | None,
    session_id: str | None,
    user_token: str | None = None,
    mint_file: Path | str | None = DEFAULT_MINT_FILE,
) -> tuple[dict[str, str | None], dict[str, str]]:
    """Fill in whatever the caller did not pass, and say where it came from.

    Order per value: argument, then `ECG_SIM_*` environment variable, then
    `.smoke/mint.txt`. Returns `(values, sources)`; a value found nowhere stays
    `None` and the caller decides whether that is fatal - `--device-token`
    without a session is a useful heartbeat-only run, so this does not invent an
    error on its own.
    """
    values: dict[str, str | None] = {}
    sources: dict[str, str] = {}

    for name, given, env_name, file_key in (
        ("device_token", device_token, "DEVICE_TOKEN", "DEVICE_TOKEN"),
        ("session_id", session_id, "SESSION_ID", "SESSION_ID"),
        ("user_token", user_token, "USER_TOKEN", "USER_TOKEN"),
    ):
        if given:
            values[name], sources[name] = given, "argument"
            continue
        from_env = os.environ.get(ENV_PREFIX + env_name)
        if from_env:
            values[name], sources[name] = from_env, "environment"
            continue
        values[name] = None

    file_values: dict[str, str] = {}
    if mint_file is not None:
        file_values = parse_mint_file(mint_file)

    for name, file_key in (
        ("device_token", "DEVICE_TOKEN"),
        ("session_id", "SESSION_ID"),
        ("user_token", "USER_TOKEN"),
    ):
        if not values[name] and file_values.get(file_key):
            values[name] = file_values[file_key]
            sources[name] = f"{Path(mint_file).name}"

    return values, sources


#: `ECG_SIM_<NAME>` -> how to read it. Only the values that are genuinely
#: useful from a shell are here; a smoke script sets the token, the session and
#: the duration and leaves everything else at its default.
_ENV_READERS: dict[str, tuple[str, type]] = {
    "BASE_URL": ("base_url", str),
    "DURATION_SECONDS": ("duration_seconds", float),
    "INTERVAL_SECONDS": ("interval_seconds", float),
    "HEARTBEAT_SECONDS": ("heartbeat_seconds", float),
    "OFFLINE_AFTER_SECONDS": ("offline_after_seconds", float),
    "ECG": ("ecg", bool),
    "ECG_SOURCE": ("ecg_source", str),
    "ECG_RECORD": ("ecg_record", str),
    "ECG_DATA_DIR": ("ecg_data_dir", str),
    "ECG_DOWNLOAD": ("ecg_download", bool),
    "ECG_CHUNK_SECONDS": ("ecg_chunk_seconds", float),
    "ECG_SAMPLE_RATE_HZ": ("ecg_sample_rate_hz", int),
    "NOISE": ("noise", bool),
    "DROP_CHUNKS": ("drop_chunks", float),
    "RESEND_CHUNKS": ("resend_chunks", float),
    "TIMEOUT_SECONDS": ("timeout_seconds", float),
    "MAX_ATTEMPTS": ("max_attempts", int),
    "SEED": ("seed", int),
    "OUTPUT_JSON": ("output_json", str),
    "VERBOSE": ("verbose", bool),
}

_TRUE = {"1", "true", "yes", "on"}


def _read(kind: type, raw: str):
    """Turn an environment string into a value of the field's type."""
    text = raw.strip()
    if kind is bool:
        return text.lower() in _TRUE
    return kind(text)


def config_from_env(**overrides) -> Config:
    """A `Config` built from `ECG_SIM_*` environment variables plus overrides.

    An override of `None` means "not given on the command line", so the
    environment value (if any) survives. An explicit command-line value always
    wins over the environment, which is what a user expects.
    """
    config = Config()
    for env_name, (attribute, kind) in _ENV_READERS.items():
        raw = os.environ.get(ENV_PREFIX + env_name)
        if raw is None or raw == "":
            continue
        setattr(config, attribute, _read(kind, raw))

    for name, value in overrides.items():
        if value is not None:
            setattr(config, name, value)
    return config


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_ECG_CHUNK_SECONDS",
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_MINT_FILE",
    "ENV_PREFIX",
    "REPO_ROOT",
    "Config",
    "ConfigError",
    "config_from_env",
    "parse_mint_file",
    "resolve_session_values",
]
