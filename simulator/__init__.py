"""The ECG telemetry simulator - Phase 3.

It plays a device: a heartbeat on `POST /sensor/connect`, four scalar readings on
`POST /sensor/data`, and ECG chunks on `POST /sensor/ecg`, all against the
Phase 2 FastAPI service, exactly as the ESP32 firmware does.

    python -m simulator --help
    python -m simulator --duration 30 --ecg
    python -m simulator --ecg --noise --drop-chunks 0.1 --resend-chunks 0.1

Layers, bottom up:

    config.py      where the settings come from (args, env, .smoke/mint.txt)
    ranges.py      the Phase 2 limits - nothing is sent without being checked
    sensors.py     temperature, SpO2, pulse, motion as bounded random walks
    ecg/           MIT-BIH or synthetic source -> noise -> resample -> chunk
    transport.py   one retrying, logging HTTP path
    simulator.py   the run loop and the summary
    cli.py         the argument parser and the exit codes

The data is synthetic. This is a screening aid, not a medical diagnosis.
"""

__all__ = ["__version__"]

__version__ = "3.0.0"
