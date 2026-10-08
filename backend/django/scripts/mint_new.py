"""Smoke-test helper: mint a NEW session plus the tokens the smoke test needs.

This is the Phase 3 sibling of `mint.py`. The difference is one line: Phase 2's
`mint.py` reuses the device's existing active session, which is right for a
repeatable "does ingestion work" check. Phase 3 counts rows per session, so it
needs a session that nothing else has ever written to - otherwise a re-send
looks like a duplicate because of an *earlier run* rather than because of the
retry being tested.

It prints the same `KEY=VALUE` lines as `mint.py`:

* DEVICE_TOKEN - a real device JWT signed by Django (tokens are per device)
* SESSION_ID   - the brand new, active session
* USER_TOKEN   - an admin access token, for `/internal/sessions` and reads
* PATIENT_ID, DEVICE_ID

Run it exactly like the other one:

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

# A new session every time, so the row counts in the smoke test belong to this
# run and nothing else.
session = new_session(device, world["patient_profile"], world["doctor"])

print("DEVICE_TOKEN=" + device_token(device))
print("SESSION_ID=" + str(session.id))
print("USER_TOKEN=" + admin_token(world["admin"]))
print("PATIENT_ID=" + str(world["patient"].id))
print("DEVICE_ID=" + str(device.id))
print("SESSION_CREATED_NEW=1")
if closed:
    print("PREVIOUS_SESSION_CLOSED=" + str(closed))
