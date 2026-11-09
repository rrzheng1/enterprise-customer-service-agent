# P5 Release Readiness — 2026-11-09

This is an engineering candidate, not a claim of production readiness or a completed GitHub publication. No commit, push, repository creation or Release publication was performed. Original development data/configuration and the 8002 stack were preserved.

## Original delivery issues and fixes

| Original issue | Resolution |
| --- | --- |
| No `.git` directory | Report tracking/history as unavailable; do not invent a clean Git-history result |
| `docs/` entirely ignored | Version public documentation and reviewed demo screenshots; private reports remain in `data/` |
| Floating Python dependencies | Commit universal locks plus verified direct constraints; retain MCP 1.x and Qdrant 1.18 contracts |
| Docker frontend stage not actually built | Build real app/MCP images from a public-only exported context; validate Linux dependencies and runtime artifacts |
| Fixed project/env/port; machine-specific setup assumptions | Parameterize full-stack env/project/port; document fresh virtual environments and clean rehearsal |
| CI only checked part of Python | Add frontend, OpenAPI/types, image builds, compatibility and redacted source/history secret checks; separate paid E2E |
| Runtime notes served as main README | Rewrite English/Chinese product-oriented entry points, organize docs and preserve historical notes |
| Missing public demo materials | Capture actual isolated seeded UI and business outcomes; no generated fake screenshots |
| Graph inspection lost tenant owner during sanitization | Retain only tenant/user identity for backend checks; add same-/cross-tenant and filtering regressions |
| Compose `start app` could rerun one-shot Seed | Put init in explicit `setup` profile; remove it as an app/MCP runtime dependency; verify review metadata hashes across restart |

## Actual checks and evidence

| Layer | Result / scope |
| --- | --- |
| Windows pytest | **146 passed**, Ruff, source compilation, dependency compatibility, OpenAPI and documentation-link checks passed |
| Clean Linux Python | **146 passed**, pip check, direct constraints/critical contracts, Ruff and OpenAPI consistency passed |
| Frontend | **18 Vitest tests**, typecheck and production build passed locally and in the clean Node build environment |
| Docker images | Real application multi-stage build and independent MCP image build passed; no source sync used as build evidence |
| Empty-volume full stack | Both first rehearsal and corrected-profile RC2 passed: fresh MySQL migrations + original Seed, PostgreSQL/Redis/Qdrant, real embedding ingestion, app/MCP startup and HTTP readiness |
| Static/UI/API | Customer, operations, Demo Lab, legacy routes, deep-link refresh, JS/CSS and same-origin API passed |
| Vite | Separate Node container on port 15173 proxies real config/session/health to the isolated backend |
| Real browser/MCP business | Three branches, approval, repeated approval, rejection and real SSE query passed on the isolated seeded stack; one demo ticket, no payment |
| Source secret scan | Official Gitleaks 8.30.1 and exact matching against local credential values: no findings in public source |
| Image layers | Application 12 filesystem layers and MCP 6 layers inspected; no private env/data or known local credential findings |
| Git tracking/history | **Not verifiable here: no Git metadata supplied** |
| Hosted Actions | Workflows configured; **not run on GitHub**; no green badge claimed |
| Restart and final profile regression | Passed on corrected-profile stacks: PostgreSQL pause/approval survives stop/start, four volumes retained, original order/review hashes and existing demo ticket count unchanged |
| Generated types | Regenerated TypeScript was byte-identical; actual FastAPI schema matched the committed OpenAPI export |
| Workflow syntax | Both workflow YAML files parsed locally; this is not a hosted Actions run |
| Private config integrity | Original `.env` and `.env.full` byte-for-byte unchanged |

Actual reports/logs are intentionally private/ignored: `data/release/rehearsal.json`, `browser.json`, `security-scan.json`, `frontend-container.json`, `lifecycle.json`, `linux-ci.log` and build logs. They are not included in public screenshots or source exports.

The first restart rehearsal detected Seed metadata refresh and failed the unchanged-facts assertion. It was not treated as a pass. The deployment profile fix separates setup from ordinary restart; no business gate or test assertion was weakened.

The normal launcher also propagates the selected project/env into explicitly requested acceptance subprocesses. A regression test prevents `--verify` for an isolated project from falling back to the developer's default stack. Final images were rebuilt after this change.

Local review resources were kept separate: development port 8002 remains untouched; rehearsals use 18002/18003 and the Vite proxy check uses 15173. Demo containers/volumes are retained, not automatically removed. Stop an unneeded rehearsal using its exact project/env as described in the deployment guide; do not use a volume-removal option for data you want to retain.

## Public presentation and attribution

- [x] English README and README_CN, clear Quick Start and configuration boundary.
- [x] Deployment/development/architecture/security/contribution guides and historical-note index.
- [x] Eight real screenshots in `docs/images/`: customer, operations, Demo Lab, HITL, SSE and three outcomes.
- [x] Accurate Mermaid architecture diagrams in README and `docs/ARCHITECTURE.md`.
- [x] Original MIT copyright **2026 Wang Jinpeng** retained; no fabricated upstream URL.
- [ ] Publisher confirms the authoritative upstream URL and any additional provenance notices.

No GIF was produced; static screenshots are genuine and sufficient to reproduce the scenario. Screenshots use a new independent database and seeded demo user/orders, not the developer's private conversation history.

## Remaining production gaps

Production SSO, public ingress/TLS/rate-limiting/operations, real payments, real evidence verification, durable cross-process jobs and a persistent SSE event log are not implemented. Hard crashes may leave unknown outcomes requiring reconciliation. Optional OpenSearch/rerank/Milvus deployments and public proxy behavior need independent validation. Dense retrieval is the validated default.

The original broad `docker-compose.yml` remains a development/reference configuration with optional services; the validated full experience uses `docker-compose.full.yml` and its launcher. Do not expose either demo configuration publicly with authentication disabled.

## Manual steps before publication

1. Confirm the original repository/source and preserve this LICENSE and additional upstream notices; fill in the authoritative URL.
2. If publishing into an existing repository, inspect `git status`, `git ls-files` and all reachable Git history with Gitleaks. Revoke/rotate any real secret found; do not assume `.gitignore` repairs history. Coordinate history rewriting explicitly if needed.
3. Initialize/select the intended repository, inspect the exact staged file list and scan it. Never stage `.env*` credentials, data, local dependencies, browser profiles or private reports. The assistant has not initialized or committed a repository.
4. Create the GitHub repository and push manually after review. Enable branch protection and let default CI run; only add a passing badge after a real successful Actions run.
5. If paid E2E is desired, create/protect the `real-e2e` Environment, configure its provider secrets/variables and deliberately dispatch with the required confirmation. Default CI needs no provider credentials.
6. Use a demo-only deployment for public demonstrations. Integrate backend-verified identity/SSO and production controls before exposing real users/data.

Current code/build/demo evidence can support a public **demo/research project** once these manual repository/provenance checks are complete. It does not certify an absent Git history or a production deployment.
