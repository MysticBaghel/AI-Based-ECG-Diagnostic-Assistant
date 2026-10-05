"""
Django settings for the config project (Django 6.1.1).

Values that differ between environments are read from the .env file at the
repository root, so no secret is hard-coded in this file.

Secrets have **no default**: a missing ``DJANGO_SECRET_KEY`` or
``JWT_SIGNING_KEY`` stops the process at startup with ``ImproperlyConfigured``
instead of silently signing real tokens with a value that is committed to the
repository. Development/test values live in ``.env.example`` and ``pytest.ini``
only.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from .env import require_env

# backend/django/
BASE_DIR = Path(__file__).resolve().parent.parent

# Repository root, where .env lives (backend/django/config/settings.py -> ../../..)
PROJECT_ROOT = BASE_DIR.parent.parent

# `override=False` (the default): a real environment variable always wins over
# the file, so a test run or a container can inject values without editing .env.
load_dotenv(PROJECT_ROOT / ".env")


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

SECRET_KEY = require_env("DJANGO_SECRET_KEY")

DEBUG = os.getenv("DJANGO_DEBUG", "True").strip().lower() in {"1", "true", "yes", "on"}

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local
    "accounts",
    "devices",
    "monitoring",
]

MIDDLEWARE = [
    # CorsMiddleware must sit above CommonMiddleware so CORS headers are added
    # even to responses short-circuited by other middleware.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Authentication
# The custom user model must be declared before the first migration runs,
# otherwise Django creates its own auth.User table and swapping later is painful.

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Django REST Framework
# JWT is the only authentication scheme: the API is consumed by the React app
# and, later, by FastAPI, neither of which uses Django sessions.

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
}


# Simple JWT
# SIGNING_KEY is deliberately separate from SECRET_KEY: FastAPI holds the same
# key and verifies tokens itself, so only this key has to be shared. Rotating
# Django's SECRET_KEY (sessions, password reset) must not invalidate API tokens,
# and the key that leaves this process must never be the one that protects
# Django's own sessions, password-reset links and signed cookies.
#
# Both keys are required from the environment (see `config/env.py`); neither
# falls back to the other and neither has a default.

JWT_SIGNING_KEY = require_env("JWT_SIGNING_KEY")

SIMPLE_JWT = {
    "ALGORITHM": "HS256",
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = "static/"


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}


# Cross-Origin Resource Sharing
# The Vite dev server runs on a different port, so the browser treats it as
# another origin and needs these headers to read API responses.

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
]


# Telemetry service (FastAPI, Phase 2)
# Django pushes each new and stopped session to FastAPI so that FastAPI can
# reject data for unknown sessions locally, without calling back. The push is
# best-effort: if the service is down, starting a session still succeeds and
# `monitoring/telemetry.py` logs a warning.

TELEMETRY_BASE_URL = os.getenv("TELEMETRY_BASE_URL", "http://127.0.0.1:8001")

TELEMETRY_SYNC_ENABLED = os.getenv(
    "TELEMETRY_SYNC_ENABLED", "True"
).strip().lower() in {"1", "true", "yes", "on"}

TELEMETRY_SYNC_TIMEOUT_SECONDS = float(os.getenv("TELEMETRY_SYNC_TIMEOUT_SECONDS", "2"))

# The user id a sync token claims. FastAPI only checks the role, and that role
# must be `admin`, so this is an identifier rather than an account: no user row
# with this id needs to exist.
TELEMETRY_SYNC_USER_ID = int(os.getenv("TELEMETRY_SYNC_USER_ID", "0"))
