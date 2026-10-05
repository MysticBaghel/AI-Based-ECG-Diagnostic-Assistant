from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/fastapi/app/core/config.py -> backend/fastapi
BASE_DIR = Path(__file__).resolve().parents[2]
# Repository root, where the shared .env file lives
ROOT_DIR = BASE_DIR.parent.parent


class Settings(BaseSettings):
    """Configuration read from the repository-root .env file.

    pydantic-settings matches each field to an environment variable of the same
    name (case-insensitively), so `fastapi_env` comes from FASTAPI_ENV.
    """

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fastapi_env: str = "development"


settings = Settings()
