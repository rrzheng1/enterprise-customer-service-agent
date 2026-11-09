"""Container-side V3 demo fixture and real MCP fault-injection checks."""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from sqlalchemy import text

from customer_service_app.core.config import get_settings
from customer_service_app.core.exceptions import AppError
from customer_service_app.infrastructure.db.session import dispose_engine, session_context
from customer_service_app.infrastructure.mcp.approval import create_approval_token
from customer_service_app.infrastructure.mcp.client import build_after_sales_mcp_client
from customer_service_app.services.business_gateway import BusinessGateway
from customer_service_app.services.confirmation_service import ConfirmationService
from customer_service_app.tools.default_registry import build_default_tool_registry


async def main(mode: str) -> dict:
    settings = get_settings()
    if settings.runtime_env != "local":
        raise RuntimeError("Verification is only allowed in the local demo environment")
    client = None
    try:
        async with session_context() as session:
            if mode in {"shipped", "delivered"}:
                await session.execute(text("UPDATE orders SET status=:status WHERE tenant_id='default' "
                    "AND user_id='u001' AND order_id='202606040003'"), {"status": mode})
                await session.commit()
                return {"fixture_status": mode}
            client = build_after_sales_mcp_client(settings)
            await client.start()

            class LoseFirstWriteResponse:
                dropped = False

                async def call_tool(self, *, name, arguments):
                    result = await client.call_tool(name=name, arguments=arguments)
                    if name == "create_refund_case" and not self.dropped:
                        self.dropped = True
                        raise TimeoutError("Injected: real MCP committed, response lost")
                    return result

            lossy = LoseFirstWriteResponse()
            gateway = BusinessGateway(session, mcp_client=lossy)
            registry = build_default_tool_registry()
            service = ConfirmationService(settings=settings, session=session, tool_registry=registry,
                                          business_gateway=gateway)
            arguments = {"order_id": "202606040003", "reason": "V3 response-loss verification " + uuid.uuid4().hex,
                         "refund_type": "return_refund"}
            action = await service.create_for_tool(tenant_id="default", user_id="u001", conversation_id=None,
                                                  tool=registry.require("create_refund_case"), arguments=arguments)
            await session.commit()
            result = await service.approve(tenant_id="default", user_id="u001", action_id=action.id)
            await session.commit()
            assert result["reconciled"] and lossy.dropped
            count = await session.scalar(text("SELECT COUNT(*) FROM support_tickets WHERE idempotency_key=:id"), {"id": action.id})
            assert count == 1 and action.status == "executed"
            token = create_approval_token(settings=settings, confirmation_id=action.id, tenant_id="default",
                user_id="u001", tool_name="create_refund_case", arguments=arguments)
            try:
                await client.call_tool(name="create_refund_case", arguments={
                    "tenant_id": "default", "user_id": "u001", "conversation_id": None,
                    **arguments, "reason": "changed after approval", "approval_token": token,
                })
            except AppError as error:
                assert error.code == "mcp_tool_error"
            else:
                raise AssertionError("MCP accepted substituted approval parameters")
            return {"response_loss_reconciled": True, "ticket_count": count, "operation_id": action.id,
                    "ticket_id": result["ticket_id"], "remote_argument_substitution_rejected": True}
    finally:
        if client:
            await client.close()
        await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["shipped", "delivered", "response-loss"])
    print(json.dumps(asyncio.run(main(parser.parse_args().mode))))
