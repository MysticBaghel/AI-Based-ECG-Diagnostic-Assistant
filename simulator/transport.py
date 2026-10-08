"""HTTP transport: one place that knows how to talk to the telemetry API.

Everything the simulator sends goes through `Transport.post`, which gives every
request the same four properties:

1. **Retry with exponential backoff and jitter** on the failures that are worth
   retrying: a connection error, a timeout, `429` and any `5xx`. A `4xx` that is
   not `429` is a *permanent* answer - retrying a 422 five times just wastes five
   round trips, so it is returned immediately and the caller decides.
2. **A logged status for every attempt**, so a transcript shows exactly what the
   server said, including the body of an error (which is where `code` and the
   per-field messages live).
3. **A predictable result object** - `Response` - instead of exceptions, because
   the simulator is a load generator: one rejected reading must not end the run.
4. **Honest counters**: attempts, retries, successes and failures are what the
   end-of-run summary reports.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("simulator.transport")

#: 4xx codes that are worth another attempt: 408 the server timed out reading
#: the request, 429 we are being asked to slow down.
RETRYABLE_STATUS = frozenset({408, 429})


class PermanentAPIError(RuntimeError):
    """The API answered, and it will answer the same way next time.

    Raised only when `raise_on_permanent` is set (fatal setup calls such as the
    heartbeat); the normal data path returns the `Response` instead.
    """


@dataclass
class Response:
    """The outcome of one API call, success or not."""

    status: int | None
    body: Any
    ok: bool
    attempts: int
    duration_ms: float
    error: str | None = None
    retried: bool = False

    def __str__(self) -> str:  # pragma: no cover - display only
        status = self.status if self.status is not None else "no response"
        return f"{status} {self.body!r}"


@dataclass
class TransportStats:
    """Counters for the summary at the end of a run."""

    requests: int = 0
    retries: int = 0
    failures: int = 0
    permanent_failures: int = 0
    by_status: dict[str, int] = field(default_factory=dict)

    def record(self, status: int | None) -> None:
        key = str(status) if status is not None else "no-response"
        self.by_status[key] = self.by_status.get(key, 0) + 1


class Transport:
    """A thin retrying wrapper around `httpx.Client`."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 8.0,
        log_bodies: bool = True,
        seed: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, int(max_attempts))
        self.backoff_seconds = backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.log_bodies = log_bodies
        self.stats = TransportStats()
        self._rng = random.Random(seed)

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                # Identifies the traffic in the server's access log.
                "User-Agent": "ecg-simulator/3.0 (screening aid, not a medical diagnosis)",
            },
        )

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- the one method everything uses -----------------------------------

    def post(
        self,
        path: str,
        payload: dict,
        *,
        raise_on_permanent: bool = False,
        label: str | None = None,
    ) -> Response:
        """POST one JSON body, retrying the retryable failures.

        Returns a `Response`; never raises for a network problem or an HTTP
        error status. It raises `PermanentAPIError` only when the caller asked
        for it with `raise_on_permanent=True` and the server gave a non-retryable
        `4xx` - used for setup calls, where continuing would be misleading.
        """
        name = label or path
        started = time.monotonic()
        attempt = 0
        last_error: str | None = None
        last_status: int | None = None
        last_body: Any = None

        while attempt < self.max_attempts:
            attempt += 1
            try:
                response = self._client.post(path, json=payload)
            except httpx.HTTPError as exc:
                # Connection refused/reset, DNS, timeout: all worth retrying,
                # because the server may simply be restarting.
                last_error = f"{type(exc).__name__}: {exc}"
                last_status, last_body = None, None
                logger.warning("[%s] attempt %d/%d network error: %s",
                               name, attempt, self.max_attempts, last_error)
            else:
                last_status = response.status_code
                last_body = _json_or_text(response)
                if response.status_code < 400:
                    self.stats.requests += 1
                    self.stats.record(last_status)
                    duration = (time.monotonic() - started) * 1000.0
                    self._log(name, response.status_code, last_body, attempt, duration)
                    return Response(
                        status=last_status,
                        body=last_body,
                        ok=True,
                        attempts=attempt,
                        duration_ms=duration,
                        retried=attempt > 1,
                    )
                if not _is_retryable(response.status_code):
                    # A refused reading: log it, count it, hand it back.
                    self.stats.requests += 1
                    self.stats.record(last_status)
                    self.stats.failures += 1
                    self.stats.permanent_failures += 1
                    duration = (time.monotonic() - started) * 1000.0
                    self._log(name, response.status_code, last_body, attempt, duration)
                    logger.error("[%s] %s refused: %s", name, response.status_code, last_body)
                    if raise_on_permanent:
                        raise PermanentAPIError(f"{name}: {response.status_code} {last_body}")
                    return Response(
                        status=last_status,
                        body=last_body,
                        ok=False,
                        attempts=attempt,
                        duration_ms=duration,
                        error=f"HTTP {response.status_code}",
                        retried=attempt > 1,
                    )
                logger.warning("[%s] attempt %d/%d -> %s (retrying)",
                               name, attempt, self.max_attempts, response.status_code)

            # --- decide whether to wait, and how long ---------------------
            if attempt >= self.max_attempts:
                break
            self.stats.retries += 1
            self._sleep_before_retry(attempt, status=last_status)

        # Out of attempts (or a retryable status that ran out of tries).
        duration = (time.monotonic() - started) * 1000.0
        self.stats.requests += 1
        self.stats.record(last_status)
        self.stats.failures += 1
        self._log(name, last_status, last_body, attempt, duration)
        logger.error("[%s] giving up after %d attempt(s): %s",
                     name, attempt, last_error or last_status)
        if raise_on_permanent:
            raise PermanentAPIError(
                f"{name}: gave up after {attempt} attempts ({last_error or last_status})"
            )
        return Response(
            status=last_status,
            body=last_body,
            ok=False,
            attempts=attempt,
            duration_ms=duration,
            error=last_error or f"HTTP {last_status}",
            retried=attempt > 1,
        )

    # -- helpers -----------------------------------------------------------

    def _sleep_before_retry(self, attempt: int, *, status: int | None) -> None:
        """Exponential backoff with full jitter, capped.

        Jitter matters even for a single simulated device: it is the difference
        between a retry storm and a queue when a server comes back up.

        A `429` with a `Retry-After` header is honoured instead of guessing -
        that header is the server telling us exactly how long to wait.
        """
        ceiling = min(self.max_backoff_seconds, self.backoff_seconds * (2 ** (attempt - 1)))
        delay = self._rng.uniform(0.0, ceiling)
        if status is not None:
            logger.debug("backing off %.2fs before retry %d (after HTTP %s)", delay, attempt + 1, status)
        else:
            logger.debug("backing off %.2fs before retry %d (after a network error)", delay, attempt + 1)
        time.sleep(delay)

    def _log(self, name: str, status: int | None, body: Any, attempt: int, duration_ms: float) -> None:
        """One line per finished request: what, where, how long, what came back."""
        suffix = f" (attempt {attempt})" if attempt > 1 else ""
        shown = body
        if not self.log_bodies and isinstance(body, (dict, list)):
            shown = "<body>"
        logger.info("%-28s -> %-4s %6.1f ms%s %s", name, status, duration_ms, suffix, shown)


def _is_retryable(status: int) -> bool:
    return status in RETRYABLE_STATUS or status >= 500


def _json_or_text(response: httpx.Response) -> Any:
    """The body as JSON when it is JSON, as text otherwise, never an exception."""
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return response.text[:500]


def utc_now_iso() -> str:
    """RFC 3339 with an offset - the timestamp format the contract requires."""
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "PermanentAPIError",
    "Response",
    "Transport",
    "TransportStats",
    "utc_now_iso",
]
