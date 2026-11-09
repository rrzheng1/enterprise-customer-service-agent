# Security

## Local demo is not a production security configuration

The default full stack is bound to loopback and uses `RUNTIME_ENV=local`, `SECURITY_ENABLED=false` for a trusted developer demonstration. It provides explicit seeded demo identities. Do not expose that mode to an untrusted network.

Outside local/development/test mode, the backend rejects requests if authentication is disabled. Production requires backend-verified JWT identity, issuer/audience, tenant and role checks, TLS and an external identity/SSO integration. Production SSO is not implemented by this project. Browser navigation is not an authorization boundary.

Refund/exchange/handoff writes retain independent confirmation, fresh business checks, signed MCP authorization, idempotency and operation reconciliation. Approval does not prove business execution. Tickets are demo applications, not real payments. Unknown execution state must be reconciled, never blindly retried.

## Credentials and reports

- Never commit `.env`, `.env.full`, generated release env files, service JWTs, API keys, database passwords, browser tokens, data, logs or traces.
- Use `.env.demo.example` or `.env.example` only as public templates. Configuration generation preserves existing DB/signing credentials and refreshes the short-lived service token for the selected stack. Never run it against another stack's volumes with different credentials.
- Browser access tokens stay in memory. Session storage contains only request/run identifiers for recovery.
- Run `python scripts/security_audit.py` and Gitleaks against source and Git history before publication. Ignore rules do not remove already tracked files or erase history.
- If a real secret ever entered Git history, revoke/rotate it first. History rewriting requires deliberate maintainer coordination; it is not performed automatically by these scripts.

This supplied workspace has no `.git` directory. Consequently its historical tracking state cannot be verified here. A clean source scan is not proof that upstream Git history is secret-free.

## Reporting a vulnerability

Do not post credentials, private transcripts or exploit details in public issues. Once the maintainer creates a GitHub repository, enable private vulnerability reporting and document a private contact. Until then, use the original private channel through which the project was supplied.
