# Repo Guidance

## Secrets

- Never commit `.env`, local token files, OAuth credentials, exported browser cookies, or coverage artifacts with machine-specific paths.
- If a new workflow introduces a secret-bearing file, update `.gitignore` in the same change.
- Use `.env.example` as the only committed environment template.
- Treat `credentials*.json`, `*token*.json`, `*.pem`, `*.p12`, `*.pfx`, and `*.key` as local-only unless the file is clearly a public test fixture.

## Checks

- Run `make typecheck`, `make lint`, and `make test` before closing work.
- Run `make coverage` when touching multiple modules or changing test coverage expectations.
- Do not silence type problems with explicit variable annotations like `my_value: Any = ...`.
- Prefer fixing the type or narrowing the value instead of suppressing the checker.
