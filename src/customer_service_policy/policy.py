from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def refund_decision(order: dict[str, Any], refund_type: str = "return_refund") -> dict[str, Any]:
    """Conservative demo policy: business-system review is authoritative, never LLM text.

    This does not automate legal refund eligibility. An approved, unexpired review
    attests that policy, category restrictions, and evidence have been checked.
    """
    if order.get("found") is not True:
        return {"allowed": False, "reason": "order_not_found", "missing_evidence": ["owned_order"]}
    if order.get("status") != "delivered":
        return {"allowed": False, "reason": "requires_further_review", "missing_evidence": ["confirmed_delivery"]}
    metadata = order.get("metadata")
    review = metadata.get("after_sale_review") if isinstance(metadata, dict) else None
    review = review if isinstance(review, dict) else {}
    required = {
        "policy": all(isinstance(review.get(key), str) and review[key].strip() for key in ("policy_id", "policy_version")),
        "quality_evidence": review.get("evidence_verified") is True,
        "category_restrictions": review.get("category_checks_passed") is True,
    }
    missing = [key for key, present in required.items() if not present]
    try:
        expiry = datetime.fromisoformat(str(review.get("valid_until", "")).replace("Z", "+00:00"))
        valid = expiry.tzinfo is not None and expiry > datetime.now(timezone.utc)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        missing.append("current_business_review")
    types = review.get("approved_refund_types")
    allowed = (not missing and review.get("status") == "approved" and isinstance(types, list)
               and all(isinstance(item, str) for item in types) and refund_type in types)
    return {"allowed": allowed, "reason": "eligible" if allowed else "requires_further_review",
            "missing_evidence": missing, "policy_id": review.get("policy_id"),
            "policy_version": review.get("policy_version")}
