"""The command line: `python -m simulator ...` or `python simulator/run.py ...`.

    --base-url        http://127.0.0.1:8001   the FastAPI telemetry service
    --device-token    a Django device JWT      \
    --session-id      a real session UUID       >  read from .smoke/mint.txt
                                                 /   when not given
    --duration        30     seconds of data
    --interval        1      seconds between scalar batches
    --ecg                    also replay ECG and `POST /sensor/ecg`
    --noise                  mains hum, baseline wander and random spikes
    --drop-chunks P          skip a chunk index with probability P
    --resend-chunks P        re-send the same chunk index with probability P
    --offline-after S        stop heartbeating after S seconds

Every flag also has an `ECG_SIM_*` environment variable, for a shell or a CI
job that would rather not build an argument list. A command-line value always
wins; `--help` lists the variables.

Exit codes: 0 the run finished, 1 a configuration or API error that made the run
impossible (an unknown session, a bad token), 2 bad arguments.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from simulator.config import (
    DEFAULT_BASE_URL,
    DEFAULT_ECG_CHUNK_SECONDS,
    DEFAULT_HEARTBEAT_SECONDS,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_MINT_FILE,
    ENV_PREFIX,
    Config,
    ConfigError,
    config_from_env,
    resolve_session_values,
)
from simulator.ecg import SOURCE_CHOICES
from simulator.simulator import ECGSimulator
from simulator.transport import PermanentAPIError, Transport

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_BAD_ARGUMENTS = 2

#: minimum --ecg-chunk-seconds: 1 s is 200 samples at 200 Hz, well inside the
#: API's 1..5000 samples per chunk, and the contract's own lower bound.
MIN_CHUNK_SECONDS = 1.0
MAX_CHUNK_SECONDS = 5.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m simulator",
        description=(
            "ECG telemetry simulator: fills the Phase 2 FastAPI service with "
            "realistic temperature, SpO2, pulse, motion and ECG chunk data. "
            "A screening aid, not a medical diagnosis."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "Values not passed here are read from the environment "
            f"({ENV_PREFIX}DEVICE_TOKEN, {ENV_PREFIX}SESSION_ID, {ENV_PREFIX}DURATION_SECONDS, ...) "
            f"and then from {DEFAULT_MINT_FILE} (written by scripts/mint_run.py)."
        ),
    )

    connection = parser.add_argument_group("connection")
    connection.add_argument(
        "--base-url",
        default=None,
        help=f"FastAPI base URL (env {ENV_PREFIX}BASE_URL)",
    )
    connection.add_argument(
        "--device-token",
        default=None,
        help=f"device JWT (env {ENV_PREFIX}DEVICE_TOKEN, else .smoke/mint.txt)",
    )
    connection.add_argument(
        "--session-id",
        default=None,
        help=f"session UUID (env {ENV_PREFIX}SESSION_ID, else .smoke/mint.txt)",
    )
    connection.add_argument(
        "--timeout-seconds",
        type=float,
        default=None,
        help=f"per-request timeout (env {ENV_PREFIX}TIMEOUT_SECONDS)",
    )
    connection.add_argument(
        "--max-attempts",
        type=int,
        default=None,
        help=f"attempts per request before giving up (env {ENV_PREFIX}MAX_ATTEMPTS)",
    )

    timing = parser.add_argument_group("timing")
    timing.add_argument(
        "--duration",
        type=float,
        default=None,
        help=f"seconds of data to produce (env {ENV_PREFIX}DURATION_SECONDS)",
    )
    timing.add_argument(
        "--interval",
        type=float,
        default=None,
        help=f"seconds between scalar batches (env {ENV_PREFIX}INTERVAL_SECONDS)",
    )
    timing.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=None,
        help=f"seconds between POST /sensor/connect heartbeats (env {ENV_PREFIX}HEARTBEAT_SECONDS)",
    )
    timing.add_argument(
        "--offline-after",
        type=float,
        default=None,
        metavar="SECONDS",
        help="stop heartbeat and data after N seconds, simulating a device going offline",
    )

    ecg = parser.add_argument_group("ECG")
    ecg.add_argument(
        "--ecg",
        action="store_true",
        default=None,
        help="replay ECG and POST /sensor/ecg chunks as well as scalar readings",
    )
    ecg.add_argument(
        "--ecg-source",
        choices=SOURCE_CHOICES,
        default=None,
        help="'auto' replays MIT-BIH through wfdb and falls back to a synthetic ECG",
    )
    ecg.add_argument(
        "--ecg-record",
        default=None,
        help="MIT-BIH record name (env ECG_SIM_ECG_RECORD)",
    )
    ecg.add_argument(
        "--ecg-data-dir",
        default=None,
        help="where MIT-BIH records are cached on disk",
    )
    ecg.add_argument(
        "--no-ecg-download",
        action="store_true",
        default=None,
        help="never reach PhysioNet; use the local cache or the synthetic generator",
    )
    ecg.add_argument(
        "--ecg-chunk-seconds",
        type=float,
        default=None,
        help=f"chunk length in seconds, {MIN_CHUNK_SECONDS:g}-{MAX_CHUNK_SECONDS:g}",
    )
    ecg.add_argument(
        "--ecg-sample-rate-hz",
        type=int,
        default=None,
        help="rate to resample the ECG to before chunking",
    )

    edge = parser.add_argument_group("edge cases")
    edge.add_argument(
        "--noise",
        action="store_true",
        default=None,
        help="add mains hum, baseline wander and random spikes to the ECG",
    )
    edge.add_argument(
        "--drop-chunks",
        type=float,
        default=None,
        metavar="PROB",
        help="skip a produced chunk with probability PROB (leaves a chunk_index gap)",
    )
    edge.add_argument(
        "--resend-chunks",
        type=float,
        default=None,
        metavar="PROB",
        help="re-send an already-sent chunk with probability PROB (proves idempotency)",
    )

    output = parser.add_argument_group("output")
    output.add_argument(
        "--seed",
        type=int,
        default=None,
        help="seed every random choice, so a run can be reproduced exactly",
    )
    output.add_argument(
        "--output-json",
        default=None,
        metavar="PATH",
        help="write the machine-readable run summary to PATH",
    )
    output.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=None,
        help="debug logging, including every retry and backoff",
    )
    output.add_argument(
        "--mint-file",
        default=str(DEFAULT_MINT_FILE),
        help="where to look for DEVICE_TOKEN/SESSION_ID when they are not given",
    )
    return parser


def configure_logging(verbose: bool) -> None:
    """One logger, timestamps, to stdout, at the verbosity asked for."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    # httpx logs one line per request at INFO, which would double every entry.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def validate(config: Config) -> None:
    """Refuse a configuration that cannot produce a useful run."""
    problems: list[str] = []
    if not config.device_token:
        problems.append(
            "--device-token is required (or ECG_SIM_DEVICE_TOKEN, or DEVICE_TOKEN "
            f"in {DEFAULT_MINT_FILE})"
        )
    if not config.session_id:
        problems.append(
            "--session-id is required (or ECG_SIM_SESSION_ID, or SESSION_ID "
            f"in {DEFAULT_MINT_FILE})"
        )
    if config.duration_seconds <= 0:
        problems.append("--duration must be greater than 0")
    if config.interval_seconds <= 0:
        problems.append("--interval must be greater than 0")
    if config.heartbeat_seconds <= 0:
        problems.append("--heartbeat-seconds must be greater than 0")
    if config.offline_after_seconds is not None and config.offline_after_seconds < 0:
        problems.append("--offline-after cannot be negative")
    for name, value in (("--drop-chunks", config.drop_chunks), ("--resend-chunks", config.resend_chunks)):
        if not 0.0 <= value <= 1.0:
            problems.append(f"{name} must be a probability between 0 and 1")
    if config.ecg:
        if not MIN_CHUNK_SECONDS <= config.ecg_chunk_seconds <= MAX_CHUNK_SECONDS:
            problems.append(
                f"--ecg-chunk-seconds must be between {MIN_CHUNK_SECONDS:g} and "
                f"{MAX_CHUNK_SECONDS:g} (the API accepts 1..5000 samples per chunk)"
            )
        if config.ecg_sample_rate_hz <= 0:
            problems.append("--ecg-sample-rate-hz must be positive")
    if config.max_attempts < 1:
        problems.append("--max-attempts must be at least 1")
    if problems:
        raise ConfigError("cannot run:\n  - " + "\n  - ".join(problems))


def build_config(args: argparse.Namespace, *, argv_provided: set[str] | None = None) -> Config:
    """Merge the environment, the command line and `.smoke/mint.txt`."""
    provided = argv_provided if argv_provided is not None else set()
    overrides = {
        name: getattr(args, name)
        for name in (
            "base_url",
            "duration_seconds",
            "interval_seconds",
            "heartbeat_seconds",
            "offline_after_seconds",
            "ecg",
            "ecg_source",
            "ecg_record",
            "ecg_data_dir",
            "ecg_chunk_seconds",
            "ecg_sample_rate_hz",
            "noise",
            "drop_chunks",
            "resend_chunks",
            "timeout_seconds",
            "max_attempts",
            "seed",
            "output_json",
            "verbose",
        )
        if getattr(args, name, None) is not None
    }
    # `--no-ecg-download` is a flag that turns something *off*, so it is the
    # only one where "present" and "true" are the same thing.
    if getattr(args, "no_ecg_download", False):
        overrides["ecg_download"] = False

    config = config_from_env(**overrides)

    values, sources = resolve_session_values(
        device_token=args.device_token,
        session_id=args.session_id,
        mint_file=args.mint_file,
    )
    config.device_token = values["device_token"]
    config.session_id = values["session_id"]
    config.user_token = values["user_token"]
    config.sources = sources
    if "base_url" not in config.sources:
        config.sources["base_url"] = "default" if "base_url" not in provided else "argument"
    return config


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # argparse cannot tell "not passed" from "passed the default", so compare
    # against the defaults to report where each value came from - which is the
    # first thing anyone asks when the simulator talks to the wrong service.
    defaults = {action.dest: action.default for action in parser._actions}  # noqa: SLF001
    provided = {
        dest
        for dest, value in vars(args).items()
        if value != defaults.get(dest)
    }

    configure_logging(bool(args.verbose))

    try:
        config = build_config(args, argv_provided=provided)
        validate(config)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        print("\n`python -m simulator --help` lists every option.", file=sys.stderr)
        return EXIT_BAD_ARGUMENTS

    logging.getLogger("simulator").info("configuration: %s", config.describe())
    if config.sources:
        logging.getLogger("simulator").info(
            "credentials: %s",
            ", ".join(f"{key} from {value}" for key, value in sorted(config.sources.items())),
        )

    transport = Transport(
        base_url=config.base_url,
        token=config.device_token or "",
        timeout_seconds=config.timeout_seconds,
        max_attempts=config.max_attempts,
        seed=config.seed,
    )
    simulator = ECGSimulator(config, transport=transport)

    try:
        with transport:
            # The first heartbeat is sent by the run loop; this is the one call
            # whose failure means "nothing else will work either" - an unknown
            # session answers 404, a bad token answers 401, and both are worth
            # failing fast on rather than retrying for thirty seconds.
            _preflight(transport, config)
            simulator.run()
    except PermanentAPIError as exc:
        print(f"\nThe API refused the run: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except KeyboardInterrupt:
        print("\ninterrupted - writing the summary for what was sent", file=sys.stderr)

    print(simulator.summary_text())
    simulator.write_summary()
    summary_path = config.output_json
    if summary_path:
        print(f"SUMMARY {_compact_summary(simulator)}")
    return EXIT_OK


def _preflight(transport: Transport, config: Config) -> None:
    """One cheap request that proves the token and the session both work."""
    logging.getLogger("simulator").info("preflight: GET /health and the device heartbeat")
    health = transport.post("/sensor/connect", {"firmware_version": "sim-3.0.0"})
    if not health.ok:
        raise PermanentAPIError(
            f"POST /sensor/connect -> {health.status} {health.body}. "
            "Check the device token, the session registry (POST /internal/sessions) "
            "and that the service is up."
        )
    logger = logging.getLogger("simulator")
    logger.info(
        "preflight ok: device %s accepted",
        (health.body or {}).get("device_id", "?"),
    )


def _compact_summary(simulator: ECGSimulator) -> str:
    """One JSON line the smoke script can parse without reading the table."""
    import json

    data = simulator.stats.as_dict()
    return json.dumps(
        {
            "readings": {name: row["stored"] for name, row in data["readings"].items()},
            "readings_total": data["readings_total"]["stored"],
            "ecg_chunks_stored": data["ecg"]["chunks_stored"],
            "ecg_chunks_unique": data["ecg"]["chunks_unique_stored"],
        },
        sort_keys=True,
    )


if __name__ == "__main__":  # pragma: no cover - exercised through run.py
    raise SystemExit(main())
