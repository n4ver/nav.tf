"""Background relay that publishes pending outbox rows to RabbitMQ."""

from __future__ import annotations

import asyncio
import logging
import os

from .outbox import flush_outbox

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = int(os.getenv("OUTBOX_POLL_INTERVAL_MS", "500"))


class OutboxWorker:
    def __init__(self, *, poll_interval_ms: int | None = None) -> None:
        self.poll_interval_ms = (
            poll_interval_ms if poll_interval_ms is not None else _POLL_INTERVAL_MS
        )
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="outbox-relay")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        self._task = None

    async def _run(self) -> None:
        interval = max(self.poll_interval_ms, 50) / 1000.0
        logger.info("Outbox relay worker started (interval=%.3fs)", interval)
        while not self._stopping.is_set():
            try:
                # Non-blocking: if a post-commit kick is relaying, skip this tick.
                count = await flush_outbox(wait_for_lock=False)
                if count:
                    logger.debug("Outbox relay published %s event(s)", count)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Outbox relay loop error")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=interval)
            except TimeoutError:
                continue


OUTBOX_WORKER = OutboxWorker()


def start_outbox_worker() -> None:
    OUTBOX_WORKER.start()


async def stop_outbox_worker() -> None:
    await OUTBOX_WORKER.stop()
