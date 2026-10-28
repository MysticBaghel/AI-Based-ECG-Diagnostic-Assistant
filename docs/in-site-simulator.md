# In-site simulator — Patients → Simulate → CSV → live graph

The pipeline exists so a demo needs no ESP32 and no terminal: an operator
registers a demo patient, hands the server an ECG file, and watches the same
live monitor a real device feeds. It is also the quickest way to confirm the
chart, the WebSocket and the analysis are working after a change.

> The data is uploaded or synthetic teaching material. A successful replay
> proves the pipeline, not a diagnosis.

## The flow

1. **Patients** page → **Simulate** (next to *Add Patient*).
2. The dialog asks for a patient name, a CSV file and — only when the file has
   no readable time column — the sample rate.
3. **Create patient and replay**:
   * `POST /api/patients/` registers a demo patient;
   * a free simulator device is reused, or `POST /api/devices/` registers one;
   * `POST /api/sessions/` starts the recording;
   * `POST /telemetry/sessions/{id}/replay` uploads the file and starts the
     stream.
4. The browser navigates to the **live monitor**. One second of signal is
   stored per second, the socket announces each chunk, and the chart draws it.
5. Stop the recording to run the analysis and generate the report as usual.

If the upload fails after the patient/session were created, the dialog says so
and **retries only the upload** — it does not create a second patient.

## What the server does with the file

`backend/fastapi/app/simulation/csv_source.py` accepts the shapes files
realistically arrive in:

| Case | Behaviour |
| --- | --- |
| One numeric column | Values are millivolts; the rate is the dialog's choice (200 Hz default). |
| `time,voltage` | The rate is inferred from the time step (seconds or milliseconds). |
| `index,time,voltage` | The leading 0,1,2… column is ignored. |
| Header row | Skipped. |
| Comma, semicolon, tab or whitespace separated | All accepted. |
| Non-numeric rows | Skipped and counted. |
| Values outside ±19 mV | Clamped to the API limit rather than rejected. |

The signal is stored at **the rate the file implies** whenever that rate is between
100 and 2000 Hz — a 300 Hz recording is reported as 300 Hz. A rate outside that
window is resampled to 200 Hz and the response says so. Uploads are capped at
**10 minutes**, every guess is returned in the response's `notes`, files are
limited to **20 MB**, and four replays can run at once.

## Why the graph works with no special case

The replay does not write to the tables directly. It builds the same
`ECGChunkRequest` / `SensorDataRequest` payloads a device sends and calls the
real ingestion handlers (`app/routes/sensor.py`). So the replay gets the same
schema validation, the same "session must be active" check, the same idempotency
constraints and the same `hub.publish()` fan-out as the firmware. The monitor,
the live analysis and the report cannot tell the difference — which is exactly
what makes them trustworthy when a device is the source.

## API

| Call | Purpose |
| --- | --- |
| `GET /simulator/scenarios` | Built-in teaching rhythms (strategy picked from the monitor, optional). |
| `POST /sessions/{id}/replay` | Body = CSV; query `name`, `rate_hz`. Starts the replay. |
| `GET /sessions/{id}/simulation` | Running or most recent run, with counters. |
| `POST /sessions/{id}/simulation/stop` | Stop early. |
| `POST /sessions/{id}/simulation` | Start one of the built-in scenarios instead of a file. |

## Provenance

Each run is stored in `simulation_runs`, and the analysis copies the source into
its stored payload. The analysis findings and the PDF report therefore open with
*"Demonstration data: this recording was replayed from the uploaded file …"*
rather than presenting replayed data as a patient recording.

## Checking it

```bash
cd backend/fastapi && pytest tests/test_csv_source.py tests/test_simulation.py
```

The tests prove the parser's cases, that the stored chunk equals the uploaded
samples, that the socket receives chunk announcements, and that the analysis
labels the recording as demonstration data.
