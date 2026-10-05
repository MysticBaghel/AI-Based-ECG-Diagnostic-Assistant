"""In-process WebSocket fan-out.

One `asyncio.Queue` per connected viewer. `POST /sensor/data` and
`POST /sensor/ecg` call `publish()` after their commit; every viewer subscribed
to that session gets the frame.

Two honest limitations, both repeated in `docs/api-contract.md` section 12:

* this is one process. Two FastAPI workers would each reach only their own
  viewers; a Redis pub/sub fan-out is the Phase 7 fix.
* a queue nobody drains (a wedged client) is dropped frame-by-frame rather than
  grown without bound, so one stalled viewer cannot exhaust the server's memory.
"""

import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

MAX_QUEUE = 100


class ReadingHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
        async with self._lock:
            self._subscribers[session_id].add(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(session_id)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(session_id, None)

    async def publish(self, session_id: str, message: dict) -> int:
        """Fan a frame out to every viewer of `session_id`; returns the count."""
        async with self._lock:
            subscribers = list(self._subscribers.get(session_id, ()))

        delivered = 0
        for queue in subscribers:
            try:
                queue.put_nowait(message)
                delivered += 1
            except asyncio.QueueFull:
                logger.warning(
                    "Dropping a live frame for session %s: viewer queue is full",
                    session_id,
                )
        return delivered

    def subscriber_count(self, session_id: str) -> int:
        return len(self._subscribers.get(session_id, ()))


#: module-level singleton, imported by the routes and the socket
hub = ReadingHub()
