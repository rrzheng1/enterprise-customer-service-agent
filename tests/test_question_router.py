from __future__ import annotations

import pytest

from customer_service_app.domain.schemas import ChatRequest
from customer_service_app.services.question_router import QuestionRouter


def test_policy_question_is_scoped_to_policy_documents() -> None:
    decision = QuestionRouter().route("七天无理由退货的条件和处理流程是什么？")

    assert decision.source == "knowledge"
    assert decision.execution_mode == "direct_answer"
    assert {"policy", "matrix", "faq", "sop"}.issubset(decision.document_types)


def test_realtime_lookup_skips_rag_and_uses_tool() -> None:
    decision = QuestionRouter().route("帮我查询订单 202607180001 现在的物流状态")

    assert decision.source == "realtime_tool"
    assert decision.execution_mode == "direct_tool"
    assert decision.document_types == []


def test_order_policy_question_uses_hybrid_route() -> None:
    decision = QuestionRouter().route(
        "订单 202607180001 是否可以退货？",
        planner_enabled=True,
    )

    assert decision.source == "hybrid"
    assert decision.execution_mode == "rag_then_tool"
    assert "policy" in decision.document_types


def test_policy_word_does_not_turn_stable_question_into_realtime_tool() -> None:
    decision = QuestionRouter().route("退款怎么处理？")

    assert decision.source == "knowledge"
    assert decision.execution_mode == "direct_answer"


def test_complex_request_enters_planner_when_enabled() -> None:
    request = ChatRequest(
        user_id="u1",
        question="先查询订单 202607180001，如果符合条件就申请退款，否则转人工",
    )

    decision = QuestionRouter().route(request.question, planner_enabled=True)

    assert decision.execution_mode == "planner"
    assert decision.reason == "complex_dependency_requires_planner"


@pytest.mark.parametrize("question", ["什么情况必须转人工？", "请不要转人工", "如果处理失败请转人工"])
def test_handoff_policy_negation_and_conditions_are_not_unconditional_requests(question):
    assert not QuestionRouter.is_explicit_handoff(question)


@pytest.mark.parametrize("question", ["创建退款前要做哪些步骤？", "机器客服什么情况必须转人工？"])
def test_business_procedure_questions_retrieve_knowledge_instead_of_executing(question):
    decision = QuestionRouter().route(question)
    assert decision.source == "knowledge"
    assert "sop" in decision.document_types


def test_enterprise_contract_and_response_queries_include_their_knowledge_scopes():
    decision = QuestionRouter().route("企业客户 P1 故障的首次人工响应目标是多久？")
    assert {"benefit", "sla"}.issubset(decision.document_types)

