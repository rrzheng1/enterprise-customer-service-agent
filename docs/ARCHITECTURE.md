# Architecture

```mermaid
flowchart TD
    UI[React: Customer / Operations / Demo Lab] -->|Same-origin HTTP + POST SSE| API[FastAPI identity and ownership checks]
    API --> Worker[Bounded in-process streaming worker / own DB session]
    API --> Approval[Independent approval and rejection API]
    Worker --> Graph[LangGraph stateful workflow]
    Graph --> RAG[Dense RAG and evidence checks]
    RAG --> Qdrant[(Qdrant)]
    RAG --> Embed[Configured embedding provider]
    Graph --> LLM[Configured chat provider]
    Graph --> Planner[Bounded Planner + conditional ToolOutcome execution]
    Planner --> Guard[Tool Registry + BusinessPolicyService]
    Approval -->|Conversation lock + fresh facts| Guard
    Guard --> Gateway[Business Gateway]
    Gateway -->|Service auth / signed approval / operation ID| MCP[After-sales MCP service]
    MCP -->|Create demo application ticket, no payment| MySQL[(MySQL: conversations / approvals / tickets)]
    Graph --> MySQL
    Graph --> PG[(PostgreSQL checkpoints)]
    Worker --> Redis[(Redis conversation locks)]
    Gateway -->|On uncertain writes| Reconcile[Query stable operation ID]
    Reconcile --> MCP
```

Browser events are an allowlist, not graph-state dumps. Nodes finish before their events are sent. Provider-native deltas are used for final tool-result synthesis; direct/cached/conditional answers are not artificially split. Confirmation-required is a paused workflow, not a completed refund.

The HTTP subscription and the Agent worker have separate lifetimes. Closing a tab detaches reception; the worker can finish and commit. Recovery reads the owned workspace. There is no persistent SSE event log and no durable cross-process task queue. Hard process termination can leave a run requiring reconciliation.

The three seeded orders are demonstrations of conservative business checks, not a complete legal refund policy or real merchant verification. The MCP service writes application tickets, never transfers funds. Dense retrieval is the default. Milvus, OpenSearch/hybrid retrieval, reranking, tracing and observability integrations remain optional.

Detailed implementation history: [V3 rules](../V3改造与验证说明.md), [SSE contract](../P4.2真实流式交互与验收.md).
