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
        self._consumer_task: asyncio.Task | None = None
        self._fallback = InMemoryBroker()
        self._prefer_memory = os.getenv("CQRS_BROKER_MODE", "").lower() == "memory"

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
                self._queue = await self._channel.declare_queue(
                    self.queue_name, durable=True
                )
                await self._queue.bind(
                    self._exchange, routing_key=f"{ROUTING_PREFIX}.#"
                )
            return

        self._connection = await connect_robust(self.url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=32)
        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
        )
        if declare_queue:
            self._queue = await self._channel.declare_queue(
                self.queue_name, durable=True
            )
            await self._queue.bind(self._exchange, routing_key=f"{ROUTING_PREFIX}.#")

    async def _consume_loop(self) -> None:
        while True:
            try:
                await self._connect(declare_queue=True)
                assert self._queue is not None
                async with self._queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        async with message.process():
                            body = json.loads(message.body.decode("utf-8"))
                            event_type = body["event_type"]
                            payload = body["payload"]
                            for callback in list(self._subscribers):
                                await callback(event_type, payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("RabbitMQ consume loop error: %s", exc)
                await asyncio.sleep(2)

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
        self._subscribers.clear()
        await self._fallback.close()


def create_broker() -> RabbitMQBroker:
    return RabbitMQBroker()


BROKER = create_broker()


async def publish_event(event_type: str, payload: Any) -> None:
    await BROKER.publish(event_type, payload)


async def close_broker() -> None:
    await BROKER.close()
