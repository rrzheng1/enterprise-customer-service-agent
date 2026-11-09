# Development

Use Python 3.11 and an isolated `.venv`. `requirements.txt` and `requirements-local.txt` point to the same committed `requirements.lock`; SQLite support is included. Do not install dependencies into a global/Conda base environment.

## Frontend

Node 24 is required for host frontend work:

```bash
npm ci --prefix frontend
npm run dev --prefix frontend
```

Open port 5173. Vite proxies to backend 8002; `BACKEND_URL=http://127.0.0.1:18002` selects an independent backend. No API credentials are embedded in the bundle. Production serves `frontend/dist` from FastAPI; deep links are explicit routes. [Frontend details](../frontend/README.md).

## Limited SQLite mode

This mode omits the full RAG/MCP/PostgreSQL approval experience. In a separate checkout or intentionally selected local `.env`, configure:

```dotenv
RUNTIME_ENV=local
SECURITY_ENABLED=false
DATABASE_URL=sqlite+aiosqlite:///./data/demo.db
RAG_ENABLED=false
MCP_AFTER_SALES_ENABLED=false
SEMANTIC_CACHE_ENABLED=false
REQUEST_LOCK_ENABLED=false
GRAPH_CHECKPOINTER=memory
V2_HIL_ENABLED=false
```

Also supply your chat provider settings. Do not overwrite a working env or point these settings at the full-stack database. Build the frontend, then run `python scripts/init_db.py`, `python scripts/seed_sample_data.py` and `python scripts/run_dev.py --host 127.0.0.1 --port 8001 --no-reload`. `start-local.cmd` assumes this configuration already exists; it does not create it automatically.

## Offline checks

Run the README commands. Default pytest uses mocked external services; it must not spend model quota. `python scripts/check_openapi.py` compares the actual API schema with the committed export. After an API change:

```bash
python scripts/export_openapi.py
npm run api:types --prefix frontend
```

CI also regenerates TypeScript and checks Git diff. Default CI includes no provider keys. The explicit E2E workflow uses the `real-e2e` GitHub Environment; configure approval protection and provider secrets before dispatching.

## Dependency updates

`requirements.in` lists intended dependencies; `constraints.txt` pins verified direct versions. Recompile both locks deliberately (uv 0.13.6 was used for this delivery):

```bash
uv pip compile requirements.in --universal --python-version 3.11 -c constraints.txt -o requirements.lock
uv pip compile mcp_services/after_sales_server/requirements.txt --universal --python-version 3.11 -c requirements.lock -o mcp_services/after_sales_server/requirements.lock
```

Install in a clean environment, run `pip check`, compatibility checks, tests and Docker builds. MCP must stay below 2 until the FastMCP integration is migrated; the default Qdrant client/server contract is 1.18. Node updates must commit the regenerated package-lock. No global npm tooling is required.

## Explicit real-provider checks

`CUSTOMER_AGENT_URL` selects the target HTTP origin; `CUSTOMER_AGENT_ENV_FILE` and `CUSTOMER_AGENT_PROJECT` select the matching Compose instance for scripts that inspect/restart containers. Do not mix these settings across stacks.

`verify_full.py` can restart the selected app, create demo tickets and expire an approval record. `verify_streaming.py` performs real model/MCP calls and creates demo tickets. `verify_v3.py --allow-fixture-mutation` additionally changes the third fixture temporarily for fault injection: only run it against a disposable isolated stack when that mutation is explicitly intended. It is not part of default CI or the P5 rehearsal.

Browser scripts require a local Playwright installation at `.local-tools/browser` (for example `npm install --prefix .local-tools/browser playwright`) and a Chromium browser. Set `BROWSER_PATH` to your executable when the Windows Edge default does not apply. Screenshots must come from seeded demo data, not private customer history.
