"""Operator CLI for the transactional outbox.

Run from ``server/`` with the command database configured:

    python -m cqrs.command_service.app.outbox_admin status
    python -m cqrs.command_service.app.outbox_admin requeue-failed [--event-id UUID ...]

``requeue-failed`` resets FAILED rows to PENDING; the running command service's
relay worker then publishes them in their original order.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from .db import SessionLocal
from .outbox import outbox_status_counts, requeue_failed_events


async def _status() -> dict[str, int]:
    async with SessionLocal() as session:
        return await outbox_status_counts(session)


async def _requeue(event_ids: list[UUID] | None) -> int:
    async with SessionLocal() as session:
        return await requeue_failed_events(session, event_ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Print outbox row counts by status")
    requeue = sub.add_parser("requeue-failed", help="Reset FAILED rows to PENDING")
    requeue.add_argument(
        "--event-id",
        action="append",
        type=UUID,
        dest="event_ids",
        help="Only requeue this event_id (repeatable). Default: all FAILED rows.",
    )
    args = parser.parse_args(argv)

    if args.command == "status":
        print(json.dumps(asyncio.run(_status()), indent=2))
    else:
        count = asyncio.run(_requeue(args.event_ids))
        print(f"Requeued {count} outbox event(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
