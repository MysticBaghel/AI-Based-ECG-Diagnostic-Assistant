"""The CSV reader behind "upload the data from anywhere".

Every case here is a file shape an operator might reasonably pick - one column,
two columns, a header, a sample-index column, milliseconds, semicolons - and
the parser has to do something defensible with each of them. The note list is
part of the contract: when the server guesses, it says so.
"""

import math

import pytest

from app.simulation.csv_source import MAX_SECONDS, parse_csv


def _signal(count: int, rate: float = 200.0) -> list[float]:
    return [round(math.sin(2 * math.pi * 1.2 * i / rate), 6) for i in range(count)]


def test_one_voltage_column_uses_the_requested_rate():
    values = _signal(400)
    text = "\n".join(str(value) for value in values)

    parsed = parse_csv(text, assumed_rate_hz=200.0)

    assert parsed.source_rate_hz == 200.0
    assert parsed.sample_rate_hz == 200
    assert parsed.samples == values
    assert parsed.duration_seconds == pytest.approx(2.0)


def test_a_header_row_is_skipped_not_counted_as_data():
    text = "voltage\n" + "\n".join(str(value) for value in _signal(200))

    parsed = parse_csv(text, assumed_rate_hz=200.0)

    assert parsed.rows_read == 200
    assert parsed.samples == _signal(200)


def test_a_time_column_in_seconds_keeps_the_files_own_rate():
    values = _signal(720, rate=360.0)
    rows = ["time,mv"] + [f"{i / 360.0:.6f},{value}" for i, value in enumerate(values)]

    parsed = parse_csv("\n".join(rows))

    assert parsed.source_rate_hz == pytest.approx(360.0, rel=1e-3)
    # The API accepts 360 Hz, so the signal is stored at 360 Hz rather than
    # being converted: 2 s stays 2 s and no sample is invented.
    assert parsed.sample_rate_hz == 360
    assert len(parsed.samples) == 720
    assert parsed.duration_seconds == pytest.approx(2.0)


def test_a_time_column_in_milliseconds_is_recognised():
    rows = ["t,value"] + [f"{i * 5},{value}" for i, value in enumerate(_signal(400, 200))]

    parsed = parse_csv("\n".join(rows), assumed_rate_hz=500.0)

    assert parsed.source_rate_hz == pytest.approx(200.0, rel=1e-3)
    assert parsed.sample_rate_hz == 200
    assert len(parsed.samples) == 400
    assert any("millisecond" in note for note in parsed.notes)


def test_a_leading_sample_index_column_is_ignored():
    values = _signal(400)
    rows = ["index,time,value"] + [
        f"{i},{i * 0.005:.3f},{value}" for i, value in enumerate(values)
    ]

    parsed = parse_csv("\n".join(rows), assumed_rate_hz=200.0)

    assert parsed.source_rate_hz == pytest.approx(200.0, rel=1e-3)
    assert len(parsed.samples) == 400
    assert any("index" in note.lower() for note in parsed.notes)


def test_semicolon_and_tab_delimited_files_parse():
    rows = ["time;value"] + [f"{i * 0.005:.3f};{value}" for i, value in enumerate(_signal(200))]

    parsed = parse_csv("\n".join(rows))

    assert parsed.source_rate_hz == pytest.approx(200.0, rel=1e-3)


def test_bad_rows_are_skipped_and_counted():
    values = _signal(100)
    rows = ["voltage"] + [str(value) for value in values[:50]] + ["not-a-number"] + [
        str(value) for value in values[50:]
    ]

    parsed = parse_csv("\n".join(rows), assumed_rate_hz=200.0)

    assert parsed.rows_skipped == 1
    assert len(parsed.samples) == 100


def test_values_are_clamped_inside_the_protocol_limit():
    text = "\n".join(["25.0", "-30.0", "0.5", "1.0"])

    parsed = parse_csv(text, assumed_rate_hz=200.0)

    assert parsed.samples == [19.0, -19.0, 0.5, 1.0]


def test_a_file_with_no_numbers_is_refused():
    with pytest.raises(ValueError):
        parse_csv("this,is,not,a,signal\n")


def test_an_absurd_requested_rate_falls_back_with_a_note():
    text = "\n".join(str(value) for value in _signal(200))

    parsed = parse_csv(text, assumed_rate_hz=1.0)

    assert parsed.source_rate_hz == 200.0
    assert any("plausible" in note for note in parsed.notes)


def test_a_very_long_file_is_trimmed_to_the_cap():
    cap = int(MAX_SECONDS * 200)
    values = [0.5] * (cap + 500)
    text = "\n".join(str(value) for value in values)

    parsed = parse_csv(text, assumed_rate_hz=200.0)

    assert len(parsed.samples) == cap
    assert any("longer than" in note for note in parsed.notes)


def test_a_300_hz_recording_is_stored_at_300_hz():
    """The report must say the rate the file actually used."""
    values = _signal(900, rate=300.0)
    rows = ["time,voltage"] + [
        f"{i / 300.0:.5f},{value}" for i, value in enumerate(values)
    ]

    parsed = parse_csv("\n".join(rows))

    assert parsed.source_rate_hz == pytest.approx(300.0, abs=0.5)
    assert parsed.sample_rate_hz == 300
    assert len(parsed.samples) == 900
    assert parsed.duration_seconds == pytest.approx(3.0)


def test_a_rate_outside_the_api_window_is_resampled_and_explained():
    values = _signal(60, rate=30.0)
    rows = ["time,value"] + [f"{i / 30.0:.5f},{value}" for i, value in enumerate(values)]

    parsed = parse_csv("\n".join(rows))

    assert parsed.sample_rate_hz == 200
    assert any("resampled" in note for note in parsed.notes)
