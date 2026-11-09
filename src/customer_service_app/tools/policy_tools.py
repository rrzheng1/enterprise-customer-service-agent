from customer_service_app.services.business_policy_service import BusinessPolicyService
from customer_service_app.services.tool_registry import ToolSpec


async def check_refund(arguments, context):
    return await BusinessPolicyService().check(tool_name="create_refund_case", arguments=arguments, context=context)


REFUND_ELIGIBILITY_TOOL = ToolSpec(
    name="check_refund_eligibility", description="基于当前用户的订单与业务系统审核记录检查退款申请条件；不能以模型推断替代。",
    parameters={"type": "object", "properties": {"order_id": {"type": "string", "minLength": 1},
                "refund_type": {"type": "string", "enum": ["return_refund", "refund_only"]}},
                "required": ["order_id"], "additionalProperties": False},
    handler=check_refund,
)
