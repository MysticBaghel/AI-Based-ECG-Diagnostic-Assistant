"""The built-in, in-site ECG simulator.

    scenarios.py  what can be simulated (normal sinus, bradycardia, ...)
    generator.py  the PQRST timeline that produces the samples
    manager.py    the running stream, written through the real ingest handlers

Importing this package does not start anything; `manager.manager` is the
process-wide instance the routes use. See `docs/in-site-simulator.md`.
"""
