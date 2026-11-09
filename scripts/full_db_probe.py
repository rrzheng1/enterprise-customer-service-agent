"""Inspect verification records inside the full-stack app container."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from customer_service_app.infrastructure.db.session import dispose_engine, session_context


async def inspect(conversation_id: str, expire: str | None) -> dict:
    try:
        async with session_context() as session:
            params = {"cid": conversation_id}
            if expire:
                await session.execute(text(
                    "UPDATE pending_actions SET expire_at=:past "
                    "WHERE id=:action AND conversation_id=:cid AND status='pending'"
                ), {**params, "action": expire,
                    "past": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)})
                await session.commit()
            tickets = await session.execute(text(
                "SELECT id, category, idempotency_key FROM support_tickets WHERE conversation_id=:cid"
            ), params)
            actions = await session.execute(text(
                "SELECT id, status FROM pending_actions WHERE conversation_id=:cid"
            ), params)
            return {"tickets": [dict(row) for row in tickets.mappings()],
                    "actions": [dict(row) for row in actions.mappings()]}
    finally:
        await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("conversation_id")
    parser.add_argument("--expire", help="Expire a pending action in this verification conversation")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(inspect(args.conversation_id, args.expire))))
