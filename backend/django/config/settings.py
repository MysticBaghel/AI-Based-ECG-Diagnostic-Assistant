"""
Django settings for the config project (Django 6.1.1).

Values that differ between environments are read from the .env file at the
repository root, so no secret is hard-coded in this file.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# backend/django/
BASE_DIR = Path(__file__).resolve().parent.parent

# Repository root, where .env lives (backend/django/config/settings.py -> ../../..)
PROJECT_ROOT = BASE_DIR.parent.parent

load_dotenv(PROJECT_ROOT / ".env")


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-fallback-for-local-dev-only")

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
# Django's SECRET_KEY (sessions, password reset) must not invalidate API tokens.

JWT_SIGNING_KEY = os.getenv("JWT_SIGNING_KEY", SECRET_KEY)

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
