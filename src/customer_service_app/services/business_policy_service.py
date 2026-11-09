from __future__ import annotations

from customer_service_policy.policy import refund_decision


class BusinessPolicyService:
    """Use fresh owned order facts and business-system review, never model assertions."""

    async def check(self, *, tool_name: str, arguments: dict, context) -> dict:
        if tool_name != "create_refund_case":
            return {"allowed": True, "reason": "not_a_refund"}
        order = await context.business_gateway.query_order_status(
            tenant_id=context.tenant_id, user_id=context.user_id,
            order_id=str(arguments.get("order_id", "")),
        )
        return refund_decision(order, str(arguments.get("refund_type", "return_refund")))
