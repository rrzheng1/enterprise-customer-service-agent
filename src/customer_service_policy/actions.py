from __future__ import annotations

import hashlib
import json
from typing import Any


def action_hash(tool_name: str, arguments: dict[str, Any], conversation_id: str | None) -> str:
    """Hash the normalized complete business action, independent of transport fields."""
    args = dict(arguments)
    for key in ("approval_token", "tenant_id", "user_id", "conversation_id"):
        args.pop(key, None)
    args.setdefault("priority", "high" if tool_name == "transfer_to_human" else "normal")
    if tool_name == "create_refund_case":
        args.setdefault("refund_type", "return_refund")
        args.setdefault("evidence_urls", [])
    payload = {"tool_name": tool_name, "arguments": args, "conversation_id": conversation_id}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()
