"""The built-in simulator: scenarios, the stream it writes, and its provenance.

The interesting assertions are not "the endpoint returned 201". They are:

* a scenario's samples produce the heart rate the scenario promises, measured by
  the real DSP - a simulator that writes rows nobody can analyse is useless;
* the stream lands in the same tables, with the same device id, as a device
  upload (it goes through the same handlers, and these tests prove it);
* the analysis records the scenario as demonstration data, so a report can
  never present it as a patient recording.
"""

import asyncio
import time
import uuid

import pytest
from sqlalchemy import func, select

from app import db
from app.dsp import analyse_chunks
from app.models import (
    DeviceConnection,
    ECGChunk,
    KnownSession,
    SensorReading,
    SimulationRun,
)
from app.simulation.generator import SAMPLE_RATE_HZ, ScenarioGenerator
from app.simulation.scenarios import SCENARIOS, get_scenario
from tests.conftest import (
    DEVICE_ID,
    SESSION_ID,
    bearer,
    issue_user_token,
)

AUTH = bearer(issue_user_token())


# --- helpers --------------------------------------------------------------


def _count(model) -> int:
    async def _run() -> int:
        async with db.SessionFactory() as session:
            return await session.scalar(select(func.count()).select_from(model))

    return asyncio.run(_run())


def _set_session_status(session_id: uuid.UUID, status: str) -> None:
    async def _run() -> None:
        async with db.SessionFactory() as session:
            known = await session.get(KnownSession, session_id)
            assert known is not None
            known.status = status
            await session.commit()

    asyncio.run(_run())


def _start(client, scenario: str = "normal_sinus", duration: float | None = 6.0):
    return client.post(
        f"/sessions/{SESSION_ID}/simulation",
        json={"scenario": scenario, "duration_seconds": duration},
        headers=AUTH,
    )


def _status(client, session_id=SESSION_ID) -> dict:
    response = client.get(f"/sessions/{session_id}/simulation", headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def _wait_for_chunks(client, minimum: int, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    last = _status(client)
    while time.monotonic() < deadline:
        last = _status(client)
        if last["chunks_sent"] >= minimum:
            return last
        time.sleep(0.1)
    raise AssertionError(f"simulator produced {last['chunks_sent']} chunks, wanted {minimum}")


def _wait_until_stopped(client, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    last = _status(client)
    while time.monotonic() < deadline:
        last = _status(client)
        if not last["running"]:
            return last
        time.sleep(0.1)
    raise AssertionError("simulator did not stop before the timeout")


# --- the scenario catalogue ----------------------------------------------


def test_scenarios_require_authentication(scoped_client):
    assert scoped_client.get("/simulator/scenarios").status_code == 401


def test_scenarios_are_listed_for_the_picker(scoped_client):
    response = scoped_client.get("/simulator/scenarios", headers=AUTH)

    assert response.status_code == 200
    payload = response.json()
    assert {item["key"] for item in payload} == set(SCENARIOS)
    assert all(item["label"] and item["description"] for item in payload)
    assert {item["key"]: item["heart_rate_bpm"] for item in payload}["normal_sinus"] == 72.0


# --- the generated signal is analysable ----------------------------------


@pytest.mark.parametrize(
    ("scenario_key", "low", "high"),
    [
        ("normal_sinus", 62.0, 82.0),
        ("sinus_bradycardia", 38.0, 54.0),
        ("sinus_tachycardia", 110.0, 145.0),
        ("atrial_fibrillation", 60.0, 160.0),
        ("frequent_pvc", 55.0, 95.0),
    ],
)
def test_each_scenario_produces_the_rhythm_it_promises(scenario_key, low, high):
    """The DSP must be able to measure what the generator produces."""
    generator = ScenarioGenerator(get_scenario(scenario_key), seed=11)
    samples: list[float] = []
    for second in range(12):
        samples.extend(generator.chunk(second, 1.0))

    result = analyse_chunks(
        [{"chunk_index": 0, "sample_rate_hz": SAMPLE_RATE_HZ, "samples": samples}],
        min_quality=35.0,
        min_seconds=2.5,
    )

    assert result["signal"]["quality"]["usable"] is True
    heart_rate = result["measurements"]["heart_rate_bpm"]
    assert low <= heart_rate <= high, (scenario_key, heart_rate)
    assert result["measurements"]["beats_detected"] >= 5


def test_irregular_rhythm_is_measurably_more_variable_than_sinus():
    def rmssd(scenario_key: str) -> float:
        generator = ScenarioGenerator(get_scenario(scenario_key), seed=3)
        samples: list[float] = []
        for second in range(15):
            samples.extend(generator.chunk(second, 1.0))
        result = analyse_chunks(
            [{"chunk_index": 0, "sample_rate_hz": SAMPLE_RATE_HZ, "samples": samples}],
            min_quality=35.0,
            min_seconds=2.5,
        )
        value = result["measurements"]["rmssd_ms"]
        assert value is not None
        return value

    assert rmssd("atrial_fibrillation") > 3.0 * rmssd("normal_sinus")
    assert rmssd("frequent_pvc") > 2.0 * rmssd("normal_sinus")


def test_two_one_second_chunks_join_without_a_seam():
    """A chunk boundary is a buffer boundary, not a signal boundary."""
    whole = ScenarioGenerator(get_scenario("normal_sinus"), seed=5).chunk(0.0, 2.0)

    generator = ScenarioGenerator(get_scenario("normal_sinus"), seed=5)
    first = generator.chunk(0.0, 1.0)
    second = generator.chunk(1.0, 1.0)

    assert first + second == whole
    assert len(whole) == 2 * SAMPLE_RATE_HZ


# --- streaming ------------------------------------------------------------


def test_start_is_refused_for_an_inactive_session(scoped_client, known_session):
    _set_session_status(SESSION_ID, "completed")

    response = _start(scoped_client)

    assert response.status_code == 409
    assert response.json()["code"] == "session_not_active"


def test_start_is_refused_for_an_unknown_session(scoped_client):
    unknown = uuid.uuid4()

    response = scoped_client.post(
        f"/sessions/{unknown}/simulation",
        json={"scenario": "normal_sinus", "duration_seconds": 2},
        headers=AUTH,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "unknown_session"


def test_start_rejects_an_unknown_scenario(scoped_client, known_session):
    response = _start(scoped_client, scenario="ventricular_fibrillation")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert "scenario" in response.text


def test_a_run_lands_in_the_same_tables_a_device_writes(scoped_client, known_session):
    started = _start(scoped_client, scenario="sinus_bradycardia", duration=6.0)
    assert started.status_code == 201, started.text
    assert started.json()["running"] is True

    reached = _wait_for_chunks(scoped_client, minimum=2)
    stopped = scoped_client.post(
        f"/sessions/{SESSION_ID}/simulation/stop", headers=AUTH
    ).json()

    assert stopped["running"] is False
    assert stopped["chunks_sent"] >= 2
    assert _count(ECGChunk) == stopped["chunks_sent"]
    assert _count(SensorReading) == 4 * stopped["chunks_sent"]

    readings = asyncio.run(_reading_counts())
    assert readings == {"temperature": stopped["chunks_sent"], "spo2": stopped["chunks_sent"],
                        "pulse": stopped["chunks_sent"], "motion": stopped["chunks_sent"]}

    # The samples are attributed to the session's own device and carry the rate
    # the analysis expects.
    async def _chunk_row():
        async with db.SessionFactory() as session:
            return await session.scalar(select(ECGChunk).limit(1))

    chunk = asyncio.run(_chunk_row())
    assert chunk.sample_rate_hz == SAMPLE_RATE_HZ
    assert chunk.device_id == DEVICE_ID

    # The stream registers the device, so the dashboard can show it online.
    assert _count(DeviceConnection) == 1


async def _reading_counts() -> dict:
    async with db.SessionFactory() as session:
        rows = await session.execute(
            select(SensorReading.sensor_type, func.count())
            .group_by(SensorReading.sensor_type)
        )
        return {sensor_type: count for sensor_type, count in rows}


def test_the_run_is_recorded_for_provenance(scoped_client, known_session):
    _start(scoped_client, scenario="atrial_fibrillation", duration=6.0)
    _wait_for_chunks(scoped_client, minimum=1)
    stopped = scoped_client.post(
        f"/sessions/{SESSION_ID}/simulation/stop", headers=AUTH
    ).json()

    async def _row():
        async with db.SessionFactory() as session:
            return await session.scalar(select(SimulationRun))

    row = asyncio.run(_row())
    assert row.scenario == "atrial_fibrillation"
    assert row.label == "Atrial fibrillation"
    assert row.status in {"stopped", "completed"}
    assert row.chunks_sent == stopped["chunks_sent"]
    assert row.stopped_at is not None


def test_second_start_while_running_is_a_conflict(scoped_client, known_session):
    assert _start(scoped_client, duration=6.0).status_code == 201
    _wait_for_chunks(scoped_client, minimum=1)

    second = _start(scoped_client, duration=6.0)

    assert second.status_code == 409
    assert second.json()["code"] == "simulation_conflict"
    scoped_client.post(f"/sessions/{SESSION_ID}/simulation/stop", headers=AUTH)


def test_the_stream_stops_when_the_recording_stops(scoped_client, known_session):
    _start(scoped_client, duration=None)  # would run for ten minutes otherwise
    _wait_for_chunks(scoped_client, minimum=1)

    _set_session_status(SESSION_ID, "completed")
    stopped = _wait_until_stopped(scoped_client, timeout=6.0)

    assert stopped["status"] == "stopped"
    assert stopped["error"] is None


def test_never_simulated_is_reported_not_guessed(scoped_client, known_session):
    status = _status(scoped_client)

    assert status["running"] is False
    assert status["status"] == "never"
    assert status["scenario"] is None
    assert status["chunks_sent"] == 0


# --- provenance in the analysis ------------------------------------------


def test_analysis_reports_the_recording_as_simulation_data(scoped_client, known_session):
    _start(scoped_client, scenario="frequent_pvc", duration=6.0)
    _wait_for_chunks(scoped_client, minimum=3)  # 3 s > the 2.5 s analysis minimum
    scoped_client.post(f"/sessions/{SESSION_ID}/simulation/stop", headers=AUTH)
    _set_session_status(SESSION_ID, "completed")

    response = scoped_client.post(f"/sessions/{SESSION_ID}/analysis", headers=AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["simulation"]["scenario"] == "frequent_pvc"
    assert payload["simulation"]["label"] == "Frequent PVCs"
    assert payload["findings"][0].startswith("Demonstration data:")
    assert "Frequent PVCs" in payload["findings"][0]


# --- CSV replay -----------------------------------------------------------


def _csv_text(seconds: float = 3.0, rate: float = 200.0) -> str:
    import math

    rows = ["time,mv"]
    for index in range(int(seconds * rate)):
        rows.append(
            f"{index / rate:.5f},{math.sin(2 * math.pi * 1.1 * index / rate):.6f}"
        )
    return "\n".join(rows)


def _replay(client, text: str, name: str = "demo.csv"):
    return client.post(
        f"/sessions/{SESSION_ID}/replay?name={name}",
        content=text,
        headers={**AUTH, "Content-Type": "text/csv"},
    )


def test_replay_rejects_a_file_with_no_numbers(scoped_client, known_session):
    response = _replay(scoped_client, "this,is,not,a,signal\n")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_replay_needs_an_active_session(scoped_client, known_session):
    _set_session_status(SESSION_ID, "completed")

    response = _replay(scoped_client, _csv_text())

    assert response.status_code == 409
    assert response.json()["code"] == "session_not_active"


def test_csv_replay_streams_the_uploaded_samples(scoped_client, known_session):
    from app.simulation.csv_source import parse_csv

    text = _csv_text(seconds=3.0)
    response = _replay(scoped_client, text)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["running"] is True
    assert body["scenario"] == "csv"
    assert body["label"] == "demo.csv"
    assert body["source_rate_hz"] == 200.0
    assert body["sample_rate_hz"] == 200
    assert body["sample_count"] == 600
    assert body["duration_seconds"] == 3.0

    _wait_for_chunks(scoped_client, minimum=1)
    scoped_client.post(f"/sessions/{SESSION_ID}/simulation/stop", headers=AUTH)

    async def _first_chunk():
        async with db.SessionFactory() as session:
            return await session.scalar(
                select(ECGChunk).where(ECGChunk.chunk_index == 0)
            )

    chunk = asyncio.run(_first_chunk())
    assert chunk is not None
    assert chunk.sample_rate_hz == SAMPLE_RATE_HZ
    # The chart is drawn from these rows, so they must be the file's samples.
    assert chunk.samples == parse_csv(text).samples[:200]


def test_replay_keeps_the_files_own_sample_rate(scoped_client, known_session):
    """A 300 Hz file is stored and analysed at 300 Hz, not converted to 200."""
    text = _csv_text(seconds=2.0, rate=300.0)

    response = _replay(scoped_client, text, name="rate-300.csv")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source_rate_hz"] == pytest.approx(300.0, abs=0.5)
    assert body["sample_rate_hz"] == 300
    assert body["sample_count"] == 600

    _wait_for_chunks(scoped_client, minimum=1)
    scoped_client.post(f"/sessions/{SESSION_ID}/simulation/stop", headers=AUTH)

    async def _first_chunk():
        async with db.SessionFactory() as session:
            return await session.scalar(
                select(ECGChunk).where(ECGChunk.chunk_index == 0)
            )

    chunk = asyncio.run(_first_chunk())
    assert chunk.sample_rate_hz == 300
    assert len(chunk.samples) == 300
