# OFF Proxy Server

Standalone project. Do not change HA List Manager or other services.

- Preserve all exported product fields, including source records without codes.
- Preserve databases, API tokens, network bindings and published datasets on updates.
- No user-facing product writes. The current API is read-only.
- Keep pet-food source unchanged until explicitly authorized; upstream is down.
- Do not claim full OFF API parity: currently only product lookup is supported.
- Run unit/HTTP tests and CLI migration/update tests. CI also runs real MongoDB tests.
- Never commit .env, product data, database files, API keys or private host details.
- All assistant commits must explicitly set and verify author AND committer:
  Nisbo <26260572+Nisbo@users.noreply.github.com>.
- Do not publish releases or rewrite history without user authorization.
