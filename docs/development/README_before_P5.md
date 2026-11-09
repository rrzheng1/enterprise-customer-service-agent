# Enterprise Customer Service Agent V3

## 产品工作空间

P4.2 已接入真实 Graph SSE、提供者文本增量与断线状态恢复，见 [流式交互与验收](../../P4.2真实流式交互与验收.md)。

新增客户聊天端 `/chat`、客服运营端 `/operations` 和场景验证台 `/demo`。原验证台保留在 `/ops` 与 `/demo/legacy`。
开发启动：先启动后端，再双击 `start-frontend.cmd`，访问 http://127.0.0.1:5173/chat 。
构建、部署、身份权限与验证步骤见 [前端说明](../../frontend/README.md)。默认首页现在是客户聊天端。

## 本地启动与完整环境验证

V3 第一阶段的条件执行、业务门禁和恢复改造见 [V3 改造与验证说明](../../V3改造与验证说明.md)。

- 已有简化体验：双击 `start-local.cmd`，访问 http://127.0.0.1:8001/ 。
- 完整容器环境：Docker 引擎可用后，双击 `start-full.cmd`，访问 http://127.0.0.1:8002/ 。
- 完整环境使用独立 `.env.full` 和 `docker-compose.full.yml`，保留原有 SQLite 数据与 `.env`。
- 启动步骤、真实验收标准与限制见 [项目启动与端到端验证（修订版）](../../项目启动与端到端验证_修订版.md)。
- 完整环境的实际验收结果写入 `data/full-validation.json`；配置或脚本准备完成不等于验收通过。

面向消费者和企业客户服务场景的 AI Agent 后端，覆盖知识问答、订单与售后业务查询、受控业务操作和人工协同。

## 项目定位

模型负责问题理解、有限规划和工具选择；后端服务负责业务事实、权限校验、风险控制、数据写入和审计。高风险写操作具备人工确认、幂等控制和恢复能力。

## 核心能力

- 多轮会话、短期上下文、长期记忆和指代改写。
- 基于 Markdown 知识库的向量检索、BM25 检索、RRF 融合和可选 Reranker。
- 知识文档的版本、生效时间、内容哈希和双索引生命周期管理。
- 有界任务规划、ReAct 执行和 LangGraph Checkpoint 持久化。
- Tool Registry、Business Gateway 和独立售后 MCP 服务。
- 读写工具分级治理、服务鉴权、调用上下文签名、Approval Token 和幂等保护。
- 人工队列、模拟坐席接管、处理结论记录和 Agent 恢复。
- 租户级模型与检索策略、缓存策略和 Token 预算控制。
- Prometheus 指标、OpenTelemetry 链路追踪和可选 LangSmith 集成。

## 技术栈

- Python 3.11+
- FastAPI、Pydantic v2、SQLAlchemy 2.x Async ORM、Alembic
- LangGraph、MCP Python SDK、OpenAI-compatible LLM/Embedding API
- MySQL、Redis、Qdrant / Milvus、OpenSearch
- Prometheus、OpenTelemetry、LangSmith
- pytest、ruff

## 目录结构

```text
enterprise-customer-service-agent-v2/
├── src/customer_service_app/
│   ├── api/                 # HTTP API
│   ├── core/                # 配置、鉴权、中间件和异常
│   ├── domain/              # 领域模型
│   ├── infrastructure/      # 数据库、缓存、检索、模型和 MCP 适配器
│   ├── services/            # 会话、记忆、规划、成本和人工协同服务
│   ├── tools/               # Agent 工具
│   └── workflows/           # LangGraph 工作流
├── mcp_services/after_sales_server/  # 独立售后 MCP 服务
├── knowledge_base/          # 客服业务知识库
├── migrations/              # Alembic 数据库迁移
├── scripts/                 # 环境、数据和开发辅助脚本
├── tests/                   # 自动化测试
├── deploy/                  # 观测组件配置
├── .env.example             # 配置项参考
├── Dockerfile
└── docker-compose.yml
```

## 相关文件

- [知识库说明](../../knowledge_base/README.md)
- [环境变量模板](../../.env.example)
- [数据库迁移](../../migrations/)
- [自动化测试](../../tests/)
- [本地基础设施配置](../../docker-compose.yml)

## License

MIT
