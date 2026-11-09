# Local Docker deployment and reproducibility

This is a trusted local demo, not a production deployment recipe. Start with the root README and `.env.demo.example`. All application dependencies come from committed Python/Node lockfiles. Host Node is unnecessary for full Docker mode.

`python scripts/run_full.py` builds real images, starts MySQL/Redis/Qdrant/PostgreSQL, applies Alembic migrations, runs the original seed script, ingests knowledge with the configured embedding provider, and starts MCP/FastAPI. `--skip-ingest` avoids a repeated embedding call when knowledge has not changed. `--skip-build` uses already-built images; do not use it for initial setup or after changing source.

Initialization is an explicit `setup` profile. The launcher targets `init` deliberately before starting the app; app/MCP do not depend on the one-shot init container. This prevents a normal `compose start app` from rerunning Seed and refreshing review metadata. Bare Compose startup without the launcher requires you to perform the setup step first.

## Separate instance

```bash
python scripts/run_full.py --env-file .env.review --source-env .env --project customer-agent-review --port 18002
```

The env file is generated privately. Existing selected database/signing credentials are retained, while the 24-hour MCP service token is refreshed. The Compose project scopes network and volumes; choose a unique project **and** port. Do not point a new set of database passwords at old volumes. Never print resolved Compose configuration; use `config --quiet`.

For subsequent Compose commands in Bash:

```bash
export CUSTOMER_AGENT_ENV_FILE="$PWD/.env.review"
docker compose --env-file .env.review -p customer-agent-review -f docker-compose.full.yml ps
docker compose --env-file .env.review -p customer-agent-review -f docker-compose.full.yml stop
docker compose --env-file .env.review -p customer-agent-review -f docker-compose.full.yml start
```

PowerShell: `$env:CUSTOMER_AGENT_ENV_FILE=(Resolve-Path .env.review).Path` before the same Docker commands. For the default `.env.full`, the override is optional.

`stop`/`start`, `restart` and `down` without `--volumes` preserve named volumes. This project does not automatically delete data. After the service JWT expires, run the launcher with the same env/project/port to renew it and recreate the app; do not generate different database credentials. The seed script maintains demonstration records, so use this launcher only for demo data, not a production database.

## Clean rehearsal tools

```bash
python scripts/release_export.py --output data/release/clean-checkout
python scripts/build_release.py --context data/release/clean-checkout
python scripts/release_rehearsal.py --context data/release/clean-checkout --project customer-agent-release-p5 --port 18002 --source-env .env
```

The exporter refuses an existing target and excludes local config, dependencies, data and reports. It never deletes a directory. Rehearsal uses the exported Compose file, separately generated secrets and dedicated volumes; it does not synchronize source into a running container. `data/release/rehearsal.json` distinguishes setup/readiness/static checks from real business E2E.

`scripts/sync_product_dev.py` is a convenience for active development only. It is not evidence of an image build or a reproducible release.

## Production requirements

Enable backend JWT verification, configure issuer/audience and a real identity provider, restrict operations roles and tenant access, and use TLS. SSO, public ingress, backups, durable cross-process jobs and operational alerting require additional integration. Preserve the business gate and MCP approval signatures.

For an SSE reverse proxy, disable response buffering, avoid compression that aggregates events, and set a suitable long-lived read timeout. Verify actual first-event latency through that proxy. Current acceptance covers local Docker networking, not a public load balancer.
