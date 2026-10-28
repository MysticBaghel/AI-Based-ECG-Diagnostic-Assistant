"""Smoke-test helper: mint a NEW session plus the tokens the smoke test needs.

It prints the same `KEY=VALUE` lines the Phase 3 script always did:

* DEVICE_TOKEN - a real device JWT signed by Django (tokens are per device)
* SESSION_ID   - the brand new, active session
* USER_TOKEN   - an admin access token, for `/internal/sessions` and reads
* PATIENT_ID   - the internal patient key stored on the session
* PATIENT_CODE - the permanent patient ID printed on reports
* DEVICE_ID

Run it:

    python backend/django/scripts/mint_new_run.py [output-file]
    $env:MINT_OUT=".smoke/mint.txt" ; python backend/django/scripts/mint_new_run.py
"""

from mint_common import (
    admin_token,
    close_active_sessions,
    device_token,
    ensure_demo_world,
    new_session,
)

world = ensure_demo_world()
device = world["device"]

# Django allows only one active session per device (a partial unique index), so
# close whatever is open first. That old session keeps its rows in FastAPI; this
# run's counts simply do not include them.
closed = close_active_sessions(device)

session = new_session(device, world["patient"], world["operator"])

print("DEVICE_TOKEN=" + device_token(device))
print("SESSION_ID=" + str(session.id))
print("USER_TOKEN=" + admin_token(world["admin"]))
print("PATIENT_ID=" + str(world["patient"].id))
print("PATIENT_CODE=" + world["patient"].patient_id)
print("DEVICE_ID=" + str(device.id))
print("SESSION_CREATED_NEW=1")
if closed:
    print("PREVIOUS_SESSION_CLOSED=" + str(closed))
