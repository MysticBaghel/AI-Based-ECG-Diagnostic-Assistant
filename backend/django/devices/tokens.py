"""Device tokens.

A device token is a JWT signed with the same key and algorithm as the user
access tokens (settings.SIMPLE_JWT), but with a different `type` claim:

    {"type": "device", "device_id": "...", "owner_id": 7, "iat": ..., "exp": ...}

It is never stored in the database - it is a bearer credential the device
presents to FastAPI, which verifies the signature locally. Long lifetime
because a device cannot perform an interactive login; revocation is done by
rotating the token or disabling the device.
"""

from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

DEVICE_TOKEN_LIFETIME = timedelta(days=365)


def issue_device_token(device):
    """Return a signed, long-lived token for `device`. Not persisted."""
    now = timezone.now()
    payload = {
        "type": "device",
        "device_id": str(device.id),
        "owner_id": device.owner_id,
        "iat": now,
        "exp": now + DEVICE_TOKEN_LIFETIME,
    }
    return jwt.encode(
        payload,
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithm=settings.SIMPLE_JWT["ALGORITHM"],
    )
