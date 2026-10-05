"""Smoke-test helper: watch one session's live readings over the WebSocket.

This is what docs/phase-2-smoke-test.md step 6 runs. It is not part of the
service - it only speaks to it.

    python scripts/ws_watch.py <session_id> <viewer_token> [device_token] [seconds]

`viewer_token` subscribes (a patient/doctor/admin access token, or the device
token itself). When `device_token` is given, the script uploads one temperature
reading a second later over HTTP so a live frame has something to carry.
"""

import asyncio
import json
import sys
import urllib.request

import websockets

BASE_HTTP = "http://127.0.0.1:8001"
BASE_WS = "ws://127.0.0.1:8001"


def _upload(session_id: str, device_token: str) -> None:
    body = json.dumps(
        {
            "session_id": session_id,
            "sensor_type": "temperature",
            "value": 37.1,
            "unit": "celsius",
        }
    ).encode()
    request = urllib.request.Request(
        f"{BASE_HTTP}/sensor/data",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {device_token}",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        print("upload ->", response.status, response.read().decode())


async def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    session_id = sys.argv[1]
    viewer_token = sys.argv[2]
    device_token = sys.argv[3] if len(sys.argv) > 3 else None
    seconds = float(sys.argv[4]) if len(sys.argv) > 4 else 10.0

    url = f"{BASE_WS}/ws/sensor?session_id={session_id}&token={viewer_token}"

    async with websockets.connect(url) as socket:
        print("connected; waiting for frames")

        async def upload_after_a_moment() -> None:
            """Give the snapshot time to arrive, then upload a reading."""
            await asyncio.sleep(1.0)
            await asyncio.to_thread(_upload, session_id, device_token)

        uploader = (
            asyncio.create_task(upload_after_a_moment()) if device_token else None
        )

        try:
            while True:
                frame = await asyncio.wait_for(socket.recv(), timeout=seconds)
                print("frame <-", frame)
                if json.loads(frame).get("event") == "reading":
                    print("SUCCESS: a live reading arrived over the socket")
                    return 0
        except asyncio.TimeoutError:
            print(f"no reading frame within {seconds}s")
            return 1
        finally:
            if uploader is not None:
                uploader.cancel()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
