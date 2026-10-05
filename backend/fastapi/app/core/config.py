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

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/fastapi/app/core/config.py -> backend/fastapi
BASE_DIR = Path(__file__).resolve().parents[2]
# Repository root, where the shared .env file lives
ROOT_DIR = BASE_DIR.parent.parent

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
load_dotenv(ROOT_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=True)


class Settings(BaseSettings):
    """Configuration read from the repository-root .env file.

    pydantic-settings matches each field to an environment variable of the same
    name (case-insensitively), so ``fastapi_env`` comes from FASTAPI_ENV.
    """

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
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
