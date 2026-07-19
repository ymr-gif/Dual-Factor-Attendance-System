"""Tiny in-process pub/sub for live tap events (Step 11).

`/tap` is a sync FastAPI handler — it runs in the threadpool, off the event loop.
The WebSocket subscribers live on the loop. So `publish()` (called from the tap
thread) must hand events to the loop safely; it uses `loop.call_soon_threadsafe`.

Fail-open: publishing is best-effort. A full/slow subscriber queue drops events,
a missing loop is a no-op — nothing here may ever break a tap.
"""

import asyncio
from typing import Any, Dict, Set

_MAX_QUEUE = 100  # per subscriber; drop when a client can't keep up

_subscribers: Set["asyncio.Queue"] = set()
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Record the running event loop (called once at startup)."""
    global _loop
    _loop = loop


async def subscribe() -> "asyncio.Queue":
    q: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE)
    _subscribers.add(q)
    return q


def unsubscribe(q: "asyncio.Queue") -> None:
    _subscribers.discard(q)


def subscriber_count() -> int:
    return len(_subscribers)


def publish(event: Dict[str, Any]) -> None:
    """Broadcast an event to all subscribers. Safe to call from any thread."""
    loop = _loop
    if loop is None or not _subscribers:
        return

    def _deliver() -> None:
        for q in list(_subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow client — drop rather than block

    try:
        loop.call_soon_threadsafe(_deliver)
    except RuntimeError:
        pass  # loop not running / closed
