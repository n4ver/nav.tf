"""Event bus: RabbitMQ producer/consumer with an in-process fallback for local/tests."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import aio_pika
from aio_pika import ExchangeType, Message, connect_robust

logger = logging.getLogger(__name__)

EventHandler = Callable[[str, Any], Awaitable[None]]

EXCHANGE_NAME = os.getenv("CQRS_EXCHANGE_NAME", "tf2-events")
QUEUE_NAME = os.getenv("CQRS_QUERY_QUEUE", "cqrs-query")
ROUTING_PREFIX = "events"
PARKING_SUFFIX = ".parking"


class NonRetryableEventError(Exception):
    """Raised by a handler when retrying the same message can never succeed."""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def is_infrastructure_error(exc: BaseException) -> bool:
    """True when ``exc`` means a dependency is unavailable, not that the message is bad.

    Covers raw socket/timeout errors from the drivers and SQLAlchemy's connection
    errors, following ``__cause__``/``__context__`` chains so wrapped errors count.
    """
    from sqlalchemy import exc as sa_exc

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (ConnectionError, TimeoutError, OSError)):
            return True
        if isinstance(
            current,
            (sa_exc.OperationalError, sa_exc.InterfaceError, sa_exc.TimeoutError),
        ):
            return True
        if isinstance(current, sa_exc.DBAPIError) and current.connection_invalidated:
            return True
        current = current.__cause__ or current.__context__
    return False


def retry_delay_seconds(attempt: int, *, base_ms: int, max_ms: int) -> float:
    """Exponential backoff: base, 2*base, 4*base, ... capped at max_ms."""
    if attempt < 1 or base_ms <= 0:
        return 0.0
    delay_ms = min(max_ms, base_ms * (2 ** (attempt - 1)))
    return max(delay_ms, 0) / 1000.0


class EventBus(Protocol):
    def subscribe(self, callback: EventHandler) -> None: ...

    async def publish(self, event_type: str, payload: Any) -> None: ...

    async def close(self) -> None: ...


class InMemoryBroker:
    """Process-local bus used for tests and RabbitMQ-unavailable fallbacks."""

    def __init__(self) -> None:
        self._subscribers: list[EventHandler] = []

    def subscribe(self, callback: EventHandler) -> None:
        self._subscribers.append(callback)

    async def publish(self, event_type: str, payload: Any) -> None:
        for callback in list(self._subscribers):
            await callback(event_type, payload)

    async def close(self) -> None:
        self._subscribers.clear()


class RabbitMQBroker:
    """Topic-exchange publisher with a durable query-side consumer queue."""

    def __init__(self, url: str | None = None, queue_name: str = QUEUE_NAME) -> None:
        self.url = url or os.getenv(
            "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
        )
        self.queue_name = queue_name
        self._subscribers: list[EventHandler] = []
        self._connection: Any = None
        self._channel: Any = None
        self._exchange: Any = None
        self._queue: Any = None
        self._parking_queue: Any = None
        self._consumer_task: asyncio.Task | None = None
        self._fallback = InMemoryBroker()
        self._prefer_memory = os.getenv("CQRS_BROKER_MODE", "").lower() == "memory"
        # Failed handlers are retried in place (the message stays unacked, so order
        # is preserved), then parked on <queue>.parking instead of being dropped.
        self.max_attempts = max(_env_int("CQRS_CONSUMER_MAX_ATTEMPTS", 5), 1)
        self.retry_base_ms = _env_int("CQRS_CONSUMER_RETRY_BASE_MS", 500)
        self.retry_max_ms = _env_int("CQRS_CONSUMER_RETRY_MAX_MS", 30000)

    @property
    def parking_queue_name(self) -> str:
        return f"{self.queue_name}{PARKING_SUFFIX}"

    def subscribe(self, callback: EventHandler) -> None:
        self._subscribers.append(callback)
        self._fallback.subscribe(callback)
        if self._prefer_memory:
            return
        if self._consumer_task is None or self._consumer_task.done():
            self._consumer_task = asyncio.create_task(self._consume_loop())

    async def publish(self, event_type: str, payload: Any) -> None:
        body = {"event_type": event_type, "payload": payload}
        if self._prefer_memory:
            await self._fallback.publish(event_type, payload)
            return

        try:
            await self._connect(declare_queue=False)
            assert self._exchange is not None
            await self._exchange.publish(
                Message(
                    json.dumps(body, default=str).encode("utf-8"),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=f"{ROUTING_PREFIX}.{event_type}",
            )
        except Exception as exc:
            if self._prefer_memory:
                logger.warning(
                    "RabbitMQ publish failed (%s); using in-process bus", exc
                )
                await self._fallback.publish(event_type, payload)
                return
            logger.error("RabbitMQ publish failed for %s: %s", event_type, exc)
            raise RuntimeError(f"Failed to publish {event_type} to RabbitMQ") from exc

    async def _connect(self, *, declare_queue: bool) -> None:
        if (
            self._connection is not None
            and self._channel is not None
            and self._exchange is not None
        ):
            if declare_queue and self._queue is None:
                await self._declare_queues()
            return

        self._connection = await connect_robust(self.url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=32)
        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
        )
        if declare_queue:
            await self._declare_queues()

    async def _declare_queues(self) -> None:
        assert self._channel is not None and self._exchange is not None
        # The main queue keeps its original (argument-free) declaration so existing
        # deployments do not hit PRECONDITION_FAILED; parking is a separate queue.
        self._queue = await self._channel.declare_queue(self.queue_name, durable=True)
        await self._queue.bind(self._exchange, routing_key=f"{ROUTING_PREFIX}.#")
        self._parking_queue = await self._channel.declare_queue(
            self.parking_queue_name, durable=True
        )

    async def _consume_loop(self) -> None:
        while True:
            try:
                await self._connect(declare_queue=True)
                assert self._queue is not None
                async with self._queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        await self._handle_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("RabbitMQ consume loop error: %s", exc)
                await asyncio.sleep(2)

    async def _handle_message(self, message: Any) -> None:
        """Dispatch one delivery: ack on success, retry with backoff, then park.

        The message is acked only after it was handled or parked. If parking itself
        fails, the exception propagates and the unacked message is redelivered.
        """
        try:
            body = json.loads(message.body.decode("utf-8"))
            event_type = body["event_type"]
            payload = body["payload"]
        except (UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            await self._park(message, error=f"malformed message: {exc!r}", attempts=0)
            await message.ack()
            return

        attempts = 0  # failures attributable to this message
        outage_retries = 0  # failures caused by an unavailable dependency
        while True:
            try:
                for callback in list(self._subscribers):
                    await callback(event_type, payload)
            except asyncio.CancelledError:
                raise
            except NonRetryableEventError as exc:
                logger.error("Parking %s (non-retryable): %s", event_type, exc)
                await self._park(message, error=repr(exc), attempts=attempts + 1)
                await message.ack()
                return
            except Exception as exc:  # noqa: BLE001
                if is_infrastructure_error(exc):
                    # The database or network is down: every message would fail the
                    # same way, so keep retrying (blocking the queue, in order)
                    # instead of draining it into the parking queue.
                    outage_retries += 1
                    delay = retry_delay_seconds(
                        outage_retries,
                        base_ms=self.retry_base_ms,
                        max_ms=self.retry_max_ms,
                    )
                    logger.warning(
                        "Dependency unavailable while handling %s, retrying in %.2fs "
                        "(not counted toward parking): %s",
                        event_type,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                attempts += 1
                if attempts >= self.max_attempts:
                    logger.error(
                        "Parking %s after %s failed attempts: %s",
                        event_type,
                        attempts,
                        exc,
                    )
                    await self._park(message, error=repr(exc), attempts=attempts)
                    await message.ack()
                    return
                delay = retry_delay_seconds(
                    attempts, base_ms=self.retry_base_ms, max_ms=self.retry_max_ms
                )
                logger.warning(
                    "Handler failed for %s (attempt %s/%s), retrying in %.2fs: %s",
                    event_type,
                    attempts,
                    self.max_attempts,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                continue
            await message.ack()
            return

    async def _park(self, message: Any, *, error: str, attempts: int) -> None:
        assert self._channel is not None
        headers = dict(getattr(message, "headers", None) or {})
        headers.update(
            {
                "x-original-routing-key": str(
                    getattr(message, "routing_key", "") or ""
                ),
                "x-error": error[:1000],
                "x-attempts": int(attempts),
            }
        )
        await self._channel.default_exchange.publish(
            Message(
                message.body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=getattr(message, "message_id", None),
                headers=headers,
            ),
            routing_key=self.parking_queue_name,
        )

    async def parked_count(self) -> int:
        await self._connect(declare_queue=True)
        assert self._channel is not None
        declared = await self._channel.declare_queue(
            self.parking_queue_name, durable=True, passive=True
        )
        return int(declared.declaration_result.message_count or 0)

    async def replay_parked(self, *, limit: int | None = None) -> int:
        """Republish parked messages to the exchange with their original routing key."""
        await self._connect(declare_queue=True)
        assert self._parking_queue is not None and self._exchange is not None
        replayed = 0
        while limit is None or replayed < limit:
            message = await self._parking_queue.get(no_ack=False, fail=False)
            if message is None:
                break
            headers = dict(message.headers or {})
            routing_key = str(headers.pop("x-original-routing-key", "") or "")
            if not routing_key:
                try:
                    event_type = json.loads(message.body.decode("utf-8"))["event_type"]
                    routing_key = f"{ROUTING_PREFIX}.{event_type}"
                except (UnicodeDecodeError, ValueError, KeyError, TypeError):
                    # Still unreadable: leave it parked for manual inspection.
                    await message.nack(requeue=True)
                    break
            headers["x-replayed-error"] = headers.pop("x-error", None)
            headers.pop("x-attempts", None)
            await self._exchange.publish(
                Message(
                    message.body,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=message.message_id,
                    headers=headers,
                ),
                routing_key=routing_key,
            )
            await message.ack()
            replayed += 1
        return replayed

    async def close(self) -> None:
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except (asyncio.CancelledError, Exception):
                pass
            self._consumer_task = None
        if self._connection is not None:
            await self._connection.close()
        self._connection = None
        self._channel = None
        self._exchange = None
        self._queue = None
        self._parking_queue = None
        self._subscribers.clear()
        await self._fallback.close()


def create_broker() -> RabbitMQBroker:
    return RabbitMQBroker()


BROKER = create_broker()


async def publish_event(event_type: str, payload: Any) -> None:
    await BROKER.publish(event_type, payload)


async def close_broker() -> None:
    await BROKER.close()
