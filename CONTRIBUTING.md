# Contributing

Use Python 3.11 and Node 24. Keep dependencies in a virtual environment and `frontend/node_modules`. Follow [development instructions](docs/DEVELOPMENT.md).

Before opening a change, run the offline Python and frontend checks, regenerate OpenAPI types if API contracts changed, and review the secret scan. Default tests must not call paid model APIs or create remote tickets. Real provider/MCP tests are explicit opt-in checks against an isolated demo stack.

Do not bypass business policy, silently approve actions, auto-retry uncertain writes, or change seeded order facts to make a test pass. Preserve the original license/attribution. Include the problem, resulting behavior, validation performed and remaining limitations in your pull request.
