"""Write a demo ECG CSV for the in-site simulator.

    python scripts/make_sample_ecg.py                     # samples/sample-ecg.csv, 30 s
    python scripts/make_sample_ecg.py --seconds 120 --out /tmp/long.csv

The file has a `time,voltage` header and millivolt values, which is the shape the
server detects on its own - no need to choose a sample rate in the dialog. It is
a teaching signal, not a patient.
"""

from __future__ import annotations

import argparse
import math
import pathlib

BEATS = (
    (-0.160, 0.022, 0.10),  # P
    (-0.018, 0.008, -0.12),  # Q
    (0.000, 0.010, 1.10),  # R
    (0.026, 0.010, -0.22),  # S
    (0.200, 0.042, 0.30),  # T
)


def sample(t: float, bpm: float) -> float:
    """The ECG at time `t`, as the sum of Gaussian P/QRS/T bumps per beat."""
    rr = 60.0 / bpm
    beat_index = math.floor(t / rr)
    value = 0.0
    for index in range(beat_index - 1, beat_index + 2):
        centre = index * rr + 0.25
        for offset, width, amplitude in BEATS:
            delta = t - (centre + offset)
            value += amplitude * math.exp(-0.5 * (delta / width) ** 2)
    value += 0.02 * math.sin(2 * math.pi * 0.25 * t)  # breathing wander
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--rate", type=float, default=200.0, help="samples per second")
    parser.add_argument("--bpm", type=float, default=72.0)
    parser.add_argument("--out", default="samples/sample-ecg.csv")
    args = parser.parse_args()

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    count = int(args.seconds * args.rate)
    with out.open("w", encoding="utf-8") as handle:
        handle.write("time,voltage\n")
        for index in range(count + 1):
            t = index / args.rate
            handle.write(f"{t:.5f},{sample(t, args.bpm):.5f}\n")

    print(f"{out}: {count + 1} rows, {args.seconds:g} s at {args.rate:g} Hz, {args.bpm:g} bpm")


if __name__ == "__main__":
    main()
