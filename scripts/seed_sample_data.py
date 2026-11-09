from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from customer_service_app.infrastructure.db.models import Order  # noqa: E402
from customer_service_app.infrastructure.db.session import dispose_engine, session_context  # noqa: E402


async def seed() -> None:
    """写入或更新一条样例订单。

    这条订单用于验证 `query_order_status` 工具和退款工单流程。
    """
    try:
        async with session_context() as session:
            result = await session.execute(
                select(Order).where(
                    Order.tenant_id == "default",
                    Order.user_id == "u001",
                    Order.order_id == "202606040001",
                )
            )
            order = result.scalar_one_or_none()
            if order is None:
                order = Order(
                    tenant_id="default",
                    user_id="u001",
                    order_id="202606040001",
                    status="shipped",
                    logistics_company="顺丰速运",
                    tracking_number="SF1234567890",
                    metadata_json={"amount": 299, "product": "智能耳机", "after_sale_days": 7},
                )
                session.add(order)
                action = "created"
            else:
                order.status = "shipped"
                order.logistics_company = "顺丰速运"
                order.tracking_number = "SF1234567890"
                order.metadata_json = {"amount": 299, "product": "智能耳机", "after_sale_days": 7}
                action = "updated"
            for number, reviewed in [("202606040002", False), ("202606040003", True)]:
                result = await session.execute(select(Order).where(
                    Order.tenant_id == "default", Order.user_id == "u001", Order.order_id == number,
                ))
                fixture = result.scalar_one_or_none()
                metadata = {"amount": 299, "product": "智能耳机", "demo_fixture": True,
                            "delivered_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}
                if reviewed:
                    metadata["after_sale_review"] = {
                        "status": "approved", "policy_id": "AFS-DEFECT-015", "policy_version": "1.4",
                        "evidence_verified": True, "category_checks_passed": True,
                        "approved_refund_types": ["return_refund", "refund_only"],
                        "valid_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                    }
                if fixture is None:
                    fixture = Order(tenant_id="default", user_id="u001", order_id=number,
                                    status="delivered", logistics_company="顺丰速运", tracking_number="DEMO" + number)
                    session.add(fixture)
                fixture.status, fixture.metadata_json = "delivered", metadata
            await session.commit()
            print(f"Sample order {action}: tenant_id=default user_id=u001 order_id=202606040001")
            print("V3 fixtures: 202606040002=review required, 202606040003=review approved (demo only)")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed())
