"""Device tokens.

A device token is a JWT signed with the same key and algorithm as the user
access tokens (settings.SIMPLE_JWT), but with a different `type` claim:

    {"type": "device", "device_id": "...", "owner_id": 7, "iat": ..., "exp": ...}

It is never stored in the database - it is a bearer credential the device
presents to FastAPI, which verifies the signature locally. The long lifetime
exists because a device cannot perform an interactive login.

What rotation and disabling actually do
--------------------------------------
They do **not** revoke an already-issued token. A device token is stateless:
Django cannot invalidate one it has already handed out, because nothing about it
is stored. Rotating issues a *new* token (the old one keeps working until it
expires) and disabling stops *new* sessions and *new* rotation from the Django
API, but a token already in a device's flash memory still verifies against
`JWT_SIGNING_KEY` until its `exp` passes - or until the signing key is rotated
for every device at once.

Honest consequence: there is no per-device revocation today. Phase 2 adds the
answer - FastAPI owns a `revoked_devices` table and refuses write endpoints for
a `device_id` listed in it - and Phase 7 wires "disable device" to write that
row.
"""

from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

DEVICE_TOKEN_LIFETIME = timedelta(days=365)


def issue_device_token(device):
    """Return a signed, long-lived token for `device`. Not persisted.

    Callers must refuse a disabled device before calling this: the token itself
    carries no "disabled" state, so once it is signed it is as good as valid
    until it expires (see the module docstring).
    """
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
