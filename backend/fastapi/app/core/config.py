"""FastAPI configuration.

Every value has a single source of truth here, and `app/core/config.py` is the
only module that reads the environment. Two rules matter:

* ``jwt_signing_key`` has **no default**. pydantic-settings raises
  ``ValidationError`` while the module is imported, so a service that was not
  given the shared key fails at startup instead of rejecting every token with a
  401 and looking like a client problem.
* ``telemetry_schema`` defaults to ``telemetry`` for PostgreSQL and is switched
  off by setting ``TELEMETRY_SCHEMA=""``. The test suite does that so it can run
  on SQLite, which has no schemas.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/fastapi/app/core/config.py -> backend/fastapi
BASE_DIR = Path(__file__).resolve().parents[2]
# Repository root, where the shared .env file lives
ROOT_DIR = BASE_DIR.parent.parent

# A test run must be hermetic: a developer's .env must not make a "missing
# key" probe succeed. FASTAPI_ENV is set before this module is imported.
_IS_TEST = os.getenv("FASTAPI_ENV", "").strip().lower() == "test"
#: In tests the environment is the only source.
_ENV_FILE = None if _IS_TEST else ROOT_DIR / ".env"

# Two layers of .env:
#
#   1. the repository-root .env, shared with Django - it holds JWT_SIGNING_KEY
#      and anything else both services agree on;
#   2. backend/fastapi/.env - this service's development defaults
#      (DATABASE_URL=SQLite, TELEMETRY_SCHEMA=""). It must **not** repeat
#      JWT_SIGNING_KEY: whichever file loads last would win, and two copies of a
#      shared secret drift.
#
# The local file overrides the shared one, and `load_dotenv` never touches a
# variable that is already in the real environment - so an operator's export
# always wins and these stay development defaults. This runs before the settings
# object reads the environment.
if not _IS_TEST:
    load_dotenv(ROOT_DIR / ".env", override=False)
    load_dotenv(BASE_DIR / ".env", override=True)


class Settings(BaseSettings):
    """Configuration read from the repository-root .env file.

    pydantic-settings matches each field to an environment variable of the same
    name (case-insensitively), so ``fastapi_env`` comes from FASTAPI_ENV.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fastapi_env: Literal["development", "test", "production"] = "development"

    # --- Database ---------------------------------------------------------
    # Async driver: psycopg 3 for PostgreSQL, aiosqlite for the test suite.
    database_url: str = "sqlite+aiosqlite:///./fastapi-dev.sqlite3"
    telemetry_schema: str = "telemetry"
    sql_echo: bool = False

    # --- Auth -------------------------------------------------------------
    # No default on purpose: missing key == startup failure.
    jwt_signing_key: str
    jwt_algorithm: Literal["HS256"] = "HS256"

    # --- Ingest limits ----------------------------------------------------
    heartbeat_threshold_seconds: int = 120
    max_payload_bytes: int = 1024 * 1024
    max_future_seconds: int = 300
    max_ecg_samples_per_chunk: int = 5000
    min_ecg_sample_rate_hz: int = 100
    max_ecg_sample_rate_hz: int = 2000

    # --- CORS -------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Analysis ---------------------------------------------------------
    #: Optional path to a trained 1-D CNN checkpoint (see app/inference.py and
    #: ml/ecg_train.ipynb). Empty means "no model is deployed": analysis still
    #: reports deterministic DSP measurements, and the ML section explicitly
    #: says unavailable.
    ecg_model_path: str | None = None
    #: Torch device for inference. ``cuda`` falls back to CPU when unavailable.
    ecg_model_device: str = "cpu"
    #: Maximum number of 30-second windows scored per recording. A 30-minute
    #: recording must not turn one analysis request into hundreds of CNN passes.
    ecg_max_windows: int = 8
    #: Minimum signal-quality score (0-100) before rhythm measurements are
    #: reported. Below it the analysis is stored as "unusable".
    min_signal_quality: float = 35.0
    #: A recording shorter than this cannot support a heart-rate estimate.
    min_analysis_seconds: float = 2.5

    # --- AI advisory ------------------------------------------------------
    #: ``template`` returns the deterministic, hard-coded advice used until the
    #: real AI API is connected. ``api`` calls an OpenAI-compatible endpoint.
    #: ``disabled`` stores an explicit "advisor unavailable" result.
    ai_advisor_provider: Literal["template", "api", "disabled"] = "template"
    ai_advisor_api_url: str | None = None
    ai_advisor_api_key: str | None = None
    ai_advisor_model: str | None = None
    ai_advisor_timeout_seconds: float = 30.0

    @computed_field
    @property
    def telemetry_schema_name(self) -> str | None:
        """The schema to put tables in, or None for "no schema" (SQLite)."""
        return self.telemetry_schema.strip() or None

    @model_validator(mode="after")
    def _sqlite_has_no_schemas(self) -> "Settings":
        """Refuse a configuration that cannot work.

        SQLite ignores `MetaData.schema` silently, which produced tables that
        could not be looked up by name again. Better to fail at startup.
        """
        if self.database_url.startswith("sqlite") and self.telemetry_schema_name:
            raise ValueError(
                'SQLite has no schemas: set TELEMETRY_SCHEMA="" or use PostgreSQL.'
            )
        return self

    @computed_field
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

# Snapshots for the parts of the app that only need a value, not the object.
JWT_SIGNING_KEY = settings.jwt_signing_key
JWT_ALGORITHM = settings.jwt_algorithm
TELEMETRY_SCHEMA = settings.telemetry_schema_name
HEARTBEAT_THRESHOLD_SECONDS = settings.heartbeat_threshold_seconds
MAX_PAYLOAD_BYTES = settings.max_payload_bytes
MAX_FUTURE_SECONDS = settings.max_future_seconds
MAX_ECG_SAMPLES_PER_CHUNK = settings.max_ecg_samples_per_chunk
MIN_ECG_SAMPLE_RATE_HZ = settings.min_ecg_sample_rate_hz
MAX_ECG_SAMPLE_RATE_HZ = settings.max_ecg_sample_rate_hz
ECG_MODEL_PATH = settings.ecg_model_path
ECG_MODEL_DEVICE = settings.ecg_model_device
ECG_MAX_WINDOWS = settings.ecg_max_windows
MIN_SIGNAL_QUALITY = settings.min_signal_quality
MIN_ANALYSIS_SECONDS = settings.min_analysis_seconds
AI_ADVISOR_PROVIDER = settings.ai_advisor_provider
AI_ADVISOR_API_URL = settings.ai_advisor_api_url
AI_ADVISOR_API_KEY = settings.ai_advisor_api_key
AI_ADVISOR_MODEL = settings.ai_advisor_model
AI_ADVISOR_TIMEOUT_SECONDS = settings.ai_advisor_timeout_seconds
