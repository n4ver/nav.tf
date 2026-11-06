"""Operator CLI for events parked by the query-side consumer.

Messages land on ``<CQRS_QUERY_QUEUE>.parking`` (default ``cqrs-query.parking``)
when a projection handler keeps failing. Fix the cause, then replay them. Run
from ``server/`` with RABBITMQ_URL configured:

    python -m cqrs.query_service.app.parking count
    python -m cqrs.query_service.app.parking replay [--limit N]

Each parked message keeps its ``x-error`` and ``x-attempts`` headers, so you can
inspect it in the RabbitMQ management UI before replaying it.
"""

from __future__ import annotations

import argparse
import asyncio

from ...shared.broker import RabbitMQBroker


async def _count() -> int:
    broker = RabbitMQBroker()
    try:
        return await broker.parked_count()
    finally:
        await broker.close()


async def _replay(limit: int | None) -> int:
    broker = RabbitMQBroker()
    try:
        return await broker.replay_parked(limit=limit)
    finally:
        await broker.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("count", help="Print the number of parked messages")
    replay = sub.add_parser("replay", help="Republish parked messages")
    replay.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    if args.command == "count":
        print(asyncio.run(_count()))
    else:
        print(f"Replayed {asyncio.run(_replay(args.limit))} parked message(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
