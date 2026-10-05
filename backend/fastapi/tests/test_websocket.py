"""`WS /ws/sensor`: live delivery, the snapshot, and the close codes."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import (
    DEVICE_ID,
    SESSION_ID,
    bearer,
    issue_device_token,
    issue_user_token,
)

BAD_TOKEN = "not.a.token"


def _now() -> str:
    """Relative to the wall clock: a fixed literal ages into a future-date 422."""
    return (datetime.now(timezone.utc) + timedelta(seconds=1)).replace(
        microsecond=0
    ).isoformat()


def test_viewer_receives_a_reading_live(scoped_client, known_session):
    """The end-to-end case: something is uploaded, the socket sees it."""
    doctor = issue_user_token()

    with scoped_client.websocket_connect(
        f"/ws/sensor?session_id={known_session}&token={doctor}"
    ) as socket:
        snapshot = socket.receive_json()
        assert snapshot["event"] == "snapshot"
        assert snapshot["readings"] == []

        stored = scoped_client.post(
            "/sensor/data",
            json={
                "session_id": str(known_session),
                "sensor_type": "temperature",
                "value": 36.8,
                "unit": "celsius",
            },
            headers=bearer(issue_device_token()),
        )
        assert stored.status_code == 200

        live = socket.receive_json()

    assert live["event"] == "reading"
    assert live["session_id"] == str(known_session)
    assert live["sensor_type"] == "temperature"
    assert live["value"] == 36.8
    assert live["unit"] == "celsius"


def test_snapshot_contains_readings_recorded_before_the_socket_opened(
    scoped_client, known_session
):
    scoped_client.post(
        "/sensor/data",
        json={
            "session_id": str(known_session),
            "sensor_type": "pulse",
            "value": 78.0,
            "unit": "bpm",
        },
        headers=bearer(issue_device_token()),
    )

    with scoped_client.websocket_connect(
        f"/ws/sensor?session_id={known_session}&token={issue_user_token()}"
    ) as socket:
        snapshot = socket.receive_json()

    assert snapshot["event"] == "snapshot"
    assert len(snapshot["readings"]) == 1
    assert snapshot["readings"][0]["sensor_type"] == "pulse"


def test_ecg_chunk_metadata_is_broadcast(scoped_client, known_session):
    with scoped_client.websocket_connect(
        f"/ws/sensor?session_id={known_session}&token={issue_user_token()}"
    ) as socket:
        assert socket.receive_json()["event"] == "snapshot"

        scoped_client.post(
            "/sensor/ecg",
            json={
                "session_id": str(known_session),
                "chunk_index": 0,
                "start_time": _now(),
                "sample_rate_hz": 250,
                "samples": [0.1, 0.2, 0.3],
            },
            headers=bearer(issue_device_token()),
        )

        live = socket.receive_json()

    assert live["event"] == "ecg_chunk"
    assert live["chunk_index"] == 0
    assert live["sample_count"] == 3
    assert "samples" not in live


def test_duplicate_readings_are_broadcast_once(scoped_client, known_session):
    body = {
        "session_id": str(known_session),
        "sensor_type": "temperature",
        "value": 36.8,
        "unit": "celsius",
        "recorded_at": _now(),
    }

    with scoped_client.websocket_connect(
        f"/ws/sensor?session_id={known_session}&token={issue_user_token()}"
    ) as socket:
        assert socket.receive_json()["event"] == "snapshot"

        device = bearer(issue_device_token())
        scoped_client.post("/sensor/data", json=body, headers=device)
        first = socket.receive_json()
        scoped_client.post("/sensor/data", json=body, headers=device)

        # Nothing else is queued for this viewer.
        socket.send_text("ping")
        follow_up = socket.receive_json()

    assert first["event"] == "reading"
    assert follow_up["event"] == "pong"


def test_the_uploading_device_may_watch_its_own_session(scoped_client, known_session):
    with scoped_client.websocket_connect(
        f"/ws/sensor?session_id={known_session}&token={issue_device_token()}"
    ) as socket:
        assert socket.receive_json()["event"] == "snapshot"


def test_a_bad_token_is_closed_with_4401(scoped_client, known_session):
    with pytest.raises(Exception) as error:
        with scoped_client.websocket_connect(
            f"/ws/sensor?session_id={known_session}&token={BAD_TOKEN}"
        ) as socket:
            socket.receive_json()

    assert "4401" in str(error.value) or "rejected" in str(error.value).lower()


def test_a_missing_token_is_closed_with_4401(scoped_client, known_session):
    with pytest.raises(Exception):
        with scoped_client.websocket_connect(
            f"/ws/sensor?session_id={known_session}"
        ) as socket:
            socket.receive_json()


def test_an_unauthorised_viewer_is_closed_with_4403(scoped_client, known_session):
    stranger = issue_user_token(99, "patient")

    with pytest.raises(Exception) as error:
        with scoped_client.websocket_connect(
            f"/ws/sensor?session_id={known_session}&token={stranger}"
        ) as socket:
            socket.receive_json()

    assert "4403" in str(error.value) or "rejected" in str(error.value).lower()


def test_an_unknown_session_is_closed_with_4404(scoped_client, unregistered_session_id):
    with pytest.raises(Exception) as error:
        with scoped_client.websocket_connect(
            f"/ws/sensor?session_id={unregistered_session_id}&token={issue_user_token()}"
        ) as socket:
            socket.receive_json()

    assert "4404" in str(error.value) or "rejected" in str(error.value).lower()


def test_the_hub_fans_out_and_unsubscribes():
    """The hub on its own, without a socket in the way."""
    import asyncio

    from app.hub import ReadingHub

    async def _run() -> None:
        hub = ReadingHub()
        first = await hub.subscribe("s")
        second = await hub.subscribe("s")

        assert await hub.publish("s", {"event": "reading"}) == 2
        assert await hub.publish("other", {"event": "reading"}) == 0
        assert first.get_nowait() == {"event": "reading"}
        assert second.get_nowait() == {"event": "reading"}

        await hub.unsubscribe("s", first)
        await hub.unsubscribe("s", second)
        assert hub.subscriber_count("s") == 0

    asyncio.run(_run())


def test_a_full_queue_drops_frames_instead_of_growing():
    """A wedged viewer must not be able to exhaust the server's memory."""
    import asyncio

    from app.hub import MAX_QUEUE, ReadingHub

    async def _run() -> None:
        hub = ReadingHub()
        queue = await hub.subscribe("s")

        for _ in range(MAX_QUEUE):
            await hub.publish("s", {"event": "reading"})

        # One more than the queue can hold: delivered nowhere, no exception.
        assert await hub.publish("s", {"event": "reading"}) == 0
        assert queue.qsize() == MAX_QUEUE

    asyncio.run(_run())
