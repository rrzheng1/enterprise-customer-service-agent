# 知序 · 企业智能客服工作空间

React 19 + TypeScript + Vite + Tailwind CSS 4 + React Router。前端调用同源 FastAPI，没有内置模型凭据，没有模拟 Token 流。

## 开发

先启动原后端（完整环境默认 `http://127.0.0.1:8002`），再在项目根目录执行：

```powershell
cd frontend
npm ci
npm run dev
```

浏览器打开 `http://127.0.0.1:5173/chat`。也可以双击根目录 `start-frontend.cmd`。
依赖只安装到 `frontend/node_modules`，不需要全局安装 npm 包，不改动 Python 环境。
连接简化后端时，在同一个 PowerShell 设置 `$env:BACKEND_URL='http://127.0.0.1:8001'` 再启动 Vite。
代理目标仅用于 Vite 服务端，不会把后端凭据注入浏览器。

| 页面 | 地址 | 功能 |
| --- | --- | --- |
| 客户服务 | `/`、`/chat`、`/chat/:conversationId` | 会话、聊天、引用、确认与工单结果 |
| 客服运营 | `/operations` | 最近会话、人工任务、工单与执行记录 |
| 场景验证 | `/demo` | 三类 V3 订单说明及嵌入原验证台 |
| 原验证台 | `/ops`、`/demo/legacy` | 原场景、工具与证据面板 |

## API 与状态

- `src/api/schema.d.ts` 从实际 FastAPI OpenAPI 生成，不手写接口字段。
- `src/api/client.ts` 负责同源 JSON 请求、错误处理和内存中的 Bearer 凭证。
- `src/api/presentation.ts` 负责状态文案、UTC 日期及真实 thread 恢复。
- `src/pages/Chat.tsx` 维护当前会话、服务端历史、请求状态与待确认动作；URL 保存会话身份，业务记录保存在后端。
- `src/components/Message.tsx` 渲染安全 Markdown、来源、实际工具结果与确认卡片。
- `src/pages/Operations.tsx` 接入现有人工分配、回复、结论提交和审核接口；每次动作等待后端确认，版本冲突直接显示错误。
- `src/hooks/useNow.ts` 更新确认过期状态。人工模式每 6 秒读取持久化消息，离开页面取消轮询。

新增 `GET /api/v1/session`、`GET /api/v1/conversations/{id}/workspace`、`GET /ops/api/conversations`、`GET /ops/api/runs` 是薄的身份/只读聚合适配层。业务写入继续使用原 `/chat`、`/confirmations`、`/human-support` API，未重写 Agent、审批、Gateway 或 MCP。
会话聚合按会话查待确认动作，避免其他会话的待办挤占结果。MySQL 秒级时间相同时按 user/assistant 排序，修复问答显示颠倒；原数据库结构不变。

审批按钮不代表成功：只有后端执行完成后才展示返回答复和数据库中的工单。请求中展示真实节点完成和工具生命周期，支持的最终汇总答复显示原生文本增量；断线后只读取持久化记录，不自动重试写操作。SSE 进度也不代表业务操作已经成功。

## 身份与部署

本地演示身份仅在后端 `RUNTIME_ENV=local/development/test` 且关闭鉴权时提供，页面明确显示“本地演示”。本地演示为可信电脑体验，不具备生产隔离。
生产环境必须启用后端 `SECURITY_ENABLED`，由外部身份系统签发带租户和角色的 JWT。页面提供令牌接入入口，仅保存在页面内存，刷新后需重新验证。尚未接入完整企业 SSO/登录服务。
普通 customer 不能访问运营会话、人工队列、执行记录或人工敏感动作；服务端校验角色、租户及用户。前端隐藏按钮不能替代权限验证。
生产服务器若关闭鉴权会直接拒绝请求。通过 TLS 反向代理部署，勿将当前本地演示 Compose 当作生产配置。
原验证台在启用鉴权后也需要有效凭证；iframe 不会继承 React 内存令牌，可独立打开并使用原页面的凭证输入。

```powershell
npm run typecheck
npm test
npm run build
```

本地 FastAPI 自动读取 `frontend/dist` 并托管静态资源。Dockerfile 使用 Node 多阶段构建后复制产物到 Python 镜像；两份 Compose 复用该 Dockerfile，不需要额外前端容器。
本轮本机 Docker 验证通过 `scripts/sync_product_dev.py` 同步构建产物及 HTTP 适配层到项目专用容器，未改动 `.env`、`.env.full` 或模型；这是开发同步，重建镜像时会被覆盖。可复现交付应通过新的 Dockerfile 构建镜像。

API 变化后在根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts/export_openapi.py
npm run api:types --prefix frontend
.\.venv\Scripts\python.exe -m pytest -q
node scripts/verify_product_ui.cjs
```

浏览器验收脚本使用 `.local-tools/browser/node_modules/playwright` 与本机 Edge；可以用 `BROWSER_PATH` 指定其他 Chromium。默认连接 8002，`CUSTOMER_AGENT_URL` 可覆盖。运行真实模型请求并生成演示工单，可能消耗模型额度；不会修改三类订单状态。报告及截图保存在被忽略的 `data/` 目录。

## P4.2 真实流式交互

当前聊天页已使用 POST `/chat/stream`：真实 Graph 节点事件与工具汇总答复的提供者原生文本增量。直接答复、缓存和确定性提示保持一次返回，不模拟 Token 流。停止接收/切换/刷新后只查询持久化 workspace，不自动重发消息；任务独立于 HTTP 连接，正式卡片和工单仍以数据库记录为准。
事件契约、断线与停机语义、实际验收、限制及发布前事项见 [P4.2 说明](../P4.2真实流式交互与验收.md)。下表保留上一轮产品化验收记录，不能代替本轮流式验收。
尚未加入消息附件、通知中心、批量工单编辑、客服绩效统计或完整 SSO；没有为这些功能制作假按钮。

## 历史：P4.1 产品化验收（2026-11-09）

以下为该阶段的历史记录，不代表当前测试数量。当前 P5 的干净构建、跨平台检查、截图与发布边界以 [发布检查清单](../docs/RELEASE_CHECKLIST.md) 为准。

| 命令 | 实际结果 |
| --- | --- |
| `npm run typecheck --prefix frontend` | TypeScript 检查通过 |
| `npm run build --prefix frontend` | 生产静态资源构建通过 |
| `npm test --prefix frontend` | 8 项测试通过：错误/鉴权传输、审批展示、安全 Markdown、UTC 时间与线程恢复 |
| `.\.venv\Scripts\python.exe -m pytest -q` | 125 项后端测试通过（原 116 项及新增 9 项权限测试） |
| `.\.venv\Scripts\python.exe -m ruff check --select E4,E7,E9,F src tests scripts mcp_services/after_sales_server/src` | 通过 |
| `node scripts/verify_product_ui.cjs` | 8002 真实后端 + 浏览器 11 项通过，包含三类 V3 条件分支、审批创建持久化 MCP 工单、拒绝无工单、刷新恢复、运营展示、兼容入口和 390px 布局；页面脚本错误为零 |
| `node scripts/verify_product_knowledge.cjs` | 5173 Vite 代理 + 真实后端 5 项通过，包含键盘操作、真实 RAG 来源展开、侧栏切换、引用恢复与无效会话错误；页面脚本错误为零 |

后端权限测试包含实际签名 customer JWT 访问运营资源被拒绝、客户不能分配/回复人工任务，以及 production 关闭鉴权时返回 401。运行中的完整环境仍是显式本地演示模式，未为了测试改动环境文件。
人工坐席的动作代码已接入原 API，本轮浏览器验收覆盖运营读取；未重新制造人工接管任务逐个点击所有人工写操作。原人工业务单元测试仍通过。
本轮未重跑完整故障注入、容器重启 checkpoint 验收或全部检索评测，也未执行新 Docker 多阶段镜像构建；不将此前验收算作本轮 E2E。最终仅补充中文状态及错误文案后重新完成静态检查、构建与单元测试。
