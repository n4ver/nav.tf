"""Unit tests for in-process event broker."""

from __future__ import annotations

import asyncio

from cqrs.shared.broker import InMemoryBroker, publish_event


def test_in_memory_broker_notifies_subscribers():
    async def run() -> None:
        broker = InMemoryBroker()
        seen: list[tuple[str, object]] = []

        async def handler(event_type: str, payload: object) -> None:
            seen.append((event_type, payload))

        broker.subscribe(handler)
        await broker.publish("TestEvent", {"value": 1})
        assert seen == [("TestEvent", {"value": 1})]
        await broker.close()

    asyncio.run(run())


def test_publish_event_uses_memory_broker_in_tests():
    async def run() -> None:
        seen: list[str] = []

        async def handler(event_type: str, _payload: object) -> None:
            seen.append(event_type)

        from cqrs.shared.broker import BROKER

        BROKER.subscribe(handler)
        await publish_event("ProbeEvent", {"probe": True})
        assert "ProbeEvent" in seen

    asyncio.run(run())
