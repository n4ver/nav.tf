"""RabbitMQ consumer retry / parking behaviour (no broker needed)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from cqrs.shared.broker import (
    NonRetryableEventError,
    RabbitMQBroker,
    retry_delay_seconds,
)


class FakeMessage:
    def __init__(self, body: bytes, *, routing_key: str = "events.MatchParsed") -> None:
        self.body = body
        self.routing_key = routing_key
        self.message_id = "msg-1"
        self.headers: dict[str, Any] = {}
        self.acked = 0

    async def ack(self) -> None:
        self.acked += 1


def _body(event_type: str = "MatchParsed", payload: Any = None) -> bytes:
    return json.dumps(
        {"event_type": event_type, "payload": payload or {"event_id": "e-1"}}
    ).encode()


@pytest.fixture
def broker(monkeypatch):
    instance = RabbitMQBroker(url="amqp://unused/")
    instance.max_attempts = 3
    instance.retry_base_ms = 0  # no real sleeping in tests
    parked: list[dict[str, Any]] = []

    async def _park(message, *, error: str, attempts: int) -> None:
        parked.append({"body": message.body, "error": error, "attempts": attempts})

    monkeypatch.setattr(instance, "_park", _park)
    instance.parked = parked  # type: ignore[attr-defined]
    return instance


def test_retry_delay_is_exponential_and_capped():
    assert retry_delay_seconds(0, base_ms=500, max_ms=30000) == 0.0
    assert retry_delay_seconds(1, base_ms=500, max_ms=30000) == 0.5
    assert retry_delay_seconds(2, base_ms=500, max_ms=30000) == 1.0
    assert retry_delay_seconds(4, base_ms=500, max_ms=30000) == 4.0
    assert retry_delay_seconds(20, base_ms=500, max_ms=30000) == 30.0
    assert retry_delay_seconds(3, base_ms=0, max_ms=30000) == 0.0


@pytest.mark.asyncio
async def test_successful_handler_acks_once(broker):
    seen: list[str] = []

    async def handler(event_type: str, _payload: Any) -> None:
        seen.append(event_type)

    broker._subscribers.append(handler)
    message = FakeMessage(_body())
    await broker._handle_message(message)

    assert seen == ["MatchParsed"]
    assert message.acked == 1
    assert broker.parked == []


@pytest.mark.asyncio
async def test_transient_failure_is_retried_in_place_then_acked(broker):
    calls = {"n": 0}

    async def flaky(_event_type: str, _payload: Any) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("db blip")

    broker._subscribers.append(flaky)
    message = FakeMessage(_body())
    await broker._handle_message(message)

    assert calls["n"] == 3
    assert message.acked == 1
    assert broker.parked == []


@pytest.mark.asyncio
async def test_persistent_failure_is_parked_not_dropped(broker):
    calls = {"n": 0}

    async def broken(_event_type: str, _payload: Any) -> None:
        calls["n"] += 1
        raise RuntimeError("projection bug")

    broker._subscribers.append(broken)
    message = FakeMessage(_body())
    await broker._handle_message(message)

    assert calls["n"] == broker.max_attempts
    assert message.acked == 1
    assert len(broker.parked) == 1
    assert broker.parked[0]["attempts"] == broker.max_attempts
    assert "projection bug" in broker.parked[0]["error"]
    assert broker.parked[0]["body"] == message.body


@pytest.mark.asyncio
async def test_non_retryable_error_is_parked_immediately(broker):
    calls = {"n": 0}

    async def reject(_event_type: str, _payload: Any) -> None:
        calls["n"] += 1
        raise NonRetryableEventError("schema mismatch")

    broker._subscribers.append(reject)
    message = FakeMessage(_body())
    await broker._handle_message(message)

    assert calls["n"] == 1
    assert message.acked == 1
    assert broker.parked[0]["attempts"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [b"not json", json.dumps({"payload": {}}).encode(), b"\xff\xfe"],
)
async def test_malformed_message_is_parked_without_calling_handlers(broker, raw):
    calls = {"n": 0}

    async def handler(_event_type: str, _payload: Any) -> None:
        calls["n"] += 1

    broker._subscribers.append(handler)
    message = FakeMessage(raw)
    await broker._handle_message(message)

    assert calls["n"] == 0
    assert message.acked == 1
    assert broker.parked[0]["attempts"] == 0
    assert "malformed" in broker.parked[0]["error"]


@pytest.mark.asyncio
async def test_message_is_not_acked_when_parking_fails(broker, monkeypatch):
    async def broken(_event_type: str, _payload: Any) -> None:
        raise RuntimeError("projection bug")

    async def park_fails(message, *, error: str, attempts: int) -> None:
        raise ConnectionError("broker gone")

    broker._subscribers.append(broken)
    monkeypatch.setattr(broker, "_park", park_fails)
    message = FakeMessage(_body())

    with pytest.raises(ConnectionError):
        await broker._handle_message(message)
    # Left unacked, so RabbitMQ redelivers it after the connection drops.
    assert message.acked == 0


@pytest.mark.asyncio
async def test_park_publishes_to_parking_queue_with_error_headers():
    published: list[tuple[Any, str]] = []

    class FakeExchange:
        async def publish(self, message, routing_key: str) -> None:
            published.append((message, routing_key))

    class FakeChannel:
        default_exchange = FakeExchange()

    broker = RabbitMQBroker(url="amqp://unused/", queue_name="cqrs-query")
    broker._channel = FakeChannel()
    message = FakeMessage(_body())
    message.headers = {"x-trace": "t-1"}

    await broker._park(message, error="boom", attempts=4)

    assert len(published) == 1
    parked, routing_key = published[0]
    assert routing_key == "cqrs-query.parking"
    assert parked.body == message.body
    assert parked.message_id == "msg-1"
    assert parked.headers["x-error"] == "boom"
    assert parked.headers["x-attempts"] == 4
    assert parked.headers["x-original-routing-key"] == "events.MatchParsed"
    assert parked.headers["x-trace"] == "t-1"


@pytest.mark.asyncio
async def test_replay_parked_republishes_with_original_routing_key(monkeypatch):
    published: list[tuple[Any, str]] = []

    class FakeExchange:
        async def publish(self, message, routing_key: str) -> None:
            published.append((message, routing_key))

    class ParkedMessage(FakeMessage):
        def __init__(self, body: bytes, headers: dict[str, Any]) -> None:
            super().__init__(body)
            self.headers = headers
            self.nacked = 0

        async def nack(self, requeue: bool = True) -> None:
            self.nacked += 1

    first = ParkedMessage(
        _body("MatchParsed"),
        {"x-original-routing-key": "events.MatchParsed", "x-error": "boom"},
    )
    # No routing-key header: falls back to events.<event_type> from the body.
    second = ParkedMessage(_body("EventCreated"), {})
    queue_items = [first, second]

    class FakeParkingQueue:
        async def get(self, *, no_ack: bool, fail: bool):
            return queue_items.pop(0) if queue_items else None

    broker = RabbitMQBroker(url="amqp://unused/")

    async def _connect(*, declare_queue: bool) -> None:
        broker._exchange = FakeExchange()
        broker._parking_queue = FakeParkingQueue()

    monkeypatch.setattr(broker, "_connect", _connect)

    assert await broker.replay_parked() == 2
    assert [key for _, key in published] == [
        "events.MatchParsed",
        "events.EventCreated",
    ]
    assert published[0][0].headers["x-replayed-error"] == "boom"
    assert "x-original-routing-key" not in published[0][0].headers
    assert first.acked == 1 and second.acked == 1


@pytest.mark.asyncio
async def test_replay_parked_respects_limit_and_leaves_unreadable(monkeypatch):
    class FakeExchange:
        def __init__(self) -> None:
            self.count = 0

        async def publish(self, message, routing_key: str) -> None:
            self.count += 1

    class Unreadable(FakeMessage):
        def __init__(self) -> None:
            super().__init__(b"not json")
            self.nacked = 0

        async def nack(self, requeue: bool = True) -> None:
            self.nacked += 1

    unreadable = Unreadable()
    items = [unreadable]

    class FakeParkingQueue:
        async def get(self, *, no_ack: bool, fail: bool):
            return items.pop(0) if items else None

    broker = RabbitMQBroker(url="amqp://unused/")
    exchange = FakeExchange()

    async def _connect(*, declare_queue: bool) -> None:
        broker._exchange = exchange
        broker._parking_queue = FakeParkingQueue()

    monkeypatch.setattr(broker, "_connect", _connect)

    assert await broker.replay_parked(limit=5) == 0
    assert unreadable.nacked == 1 and unreadable.acked == 0
    assert exchange.count == 0
    assert await broker.replay_parked(limit=0) == 0


def test_is_infrastructure_error_classification():
    from sqlalchemy.exc import IntegrityError, OperationalError

    from cqrs.shared.broker import is_infrastructure_error

    assert is_infrastructure_error(ConnectionRefusedError("db down"))
    assert is_infrastructure_error(TimeoutError())
    assert is_infrastructure_error(
        OperationalError("SELECT 1", {}, Exception("server closed the connection"))
    )
    assert not is_infrastructure_error(
        IntegrityError("INSERT", {}, Exception("duplicate key"))
    )
    assert not is_infrastructure_error(KeyError("match_id"))

    try:
        try:
            raise ConnectionResetError("reset by peer")
        except ConnectionResetError as inner:
            raise RuntimeError("projection failed") from inner
    except RuntimeError as wrapped:
        assert is_infrastructure_error(wrapped)


@pytest.mark.asyncio
async def test_outage_retries_do_not_count_toward_parking(broker):
    calls = {"n": 0}

    async def db_down_then_up(_event_type: str, _payload: Any) -> None:
        calls["n"] += 1
        if calls["n"] <= broker.max_attempts * 3:
            raise ConnectionRefusedError("postgres restarting")

    broker._subscribers.append(db_down_then_up)
    message = FakeMessage(_body())
    await broker._handle_message(message)

    assert calls["n"] == broker.max_attempts * 3 + 1
    assert message.acked == 1
    assert broker.parked == []


@pytest.mark.asyncio
async def test_outage_then_message_bug_still_parks(broker):
    calls = {"n": 0}

    async def outage_then_bug(_event_type: str, _payload: Any) -> None:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ConnectionRefusedError("postgres restarting")
        raise ValueError("bad payload field")

    broker._subscribers.append(outage_then_bug)
    message = FakeMessage(_body())
    await broker._handle_message(message)

    assert calls["n"] == 2 + broker.max_attempts
    assert broker.parked[0]["attempts"] == broker.max_attempts
    assert "bad payload field" in broker.parked[0]["error"]
