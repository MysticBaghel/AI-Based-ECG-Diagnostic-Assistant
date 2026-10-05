"""Helpers for reading required environment values.

Kept in its own module (rather than inline in ``settings.py``) for two reasons:

* ``settings.py`` reads its values at import time, which makes a missing key an
  ``ImproperlyConfigured`` raised during startup rather than a confusing failure
  later on;
* the behaviour itself is unit-testable in isolation
  (``accounts/tests.py::test_require_env_*``), without importing Django settings
  a second time.
"""

import os

from django.core.exceptions import ImproperlyConfigured


def require_env(name):
    """Return ``os.environ[name]``, or fail loudly if it is missing.

    There is deliberately **no default**. A development fallback for a secret is
    how a hard-coded key reaches production: the process starts happily, signing
    real tokens with a value that is committed to the repository.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"{name} is not set. Copy .env.example to .env and fill it in "
            f"(generate secrets with: "
            f'python -c "import secrets; print(secrets.token_urlsafe(50))").'
        )
    return value
