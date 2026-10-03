# Security

## Threat model in one paragraph

Lia is multi-tenant: many organizations share one API and one internal database, and each organization points Lia at
**its own** PostgreSQL/MySQL/CRM with credentials it entrusts to Lia. An LLM sits between the user's voice and the
tools that read and write that data, so tool arguments must be treated as untrusted input (prompt injection,
hallucination). The main assets are (1) tenant connector credentials, (2) tenant business data reachable through them,
(3) user accounts.

## Controls

| Area | Control | Where |
|------|---------|-------|
| Secrets at rest | Tenant `connector_config` is encrypted with Fernet (`CONNECTOR_ENCRYPTION_KEY`, rotation supported); legacy plaintext rows stay readable and are migrated with `python manage.py encrypt-connectors` | `app/crypto.py` |
| Secrets in transit to clients | Secret-looking keys (`password`, `secret`, `token`, `api_key`, ...) are returned as `********`; echoing the mask back on save keeps the stored value; plain members never see connector config | `app/security.py`, `routes/organizations.py` |
| Tenant isolation | `GET /organizations/<id>` only for members/admins (404 otherwise); `/organizations` scoped; every `/admin/*` route is tested to reject non-admins | routes + `tests/integration/test_admin_api.py` |
| Authentication | bcrypt; uniform "Invalid email or password" and constant-time dummy hash for unknown e-mails; login rate limit (`LOGIN_RATE_LIMIT`, per IP) plus an nginx limit; JWT lifetime `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` (default 8 h, was 24 h) | `routes/auth.py` |
| Startup safety | Refuses to start without `JWT_SECRET_KEY`; in production also rejects weak/placeholder secrets, `CORS_ORIGINS=*`, and forces `DEBUG` off | `app/config.py` |
| CORS | Explicit allow-list, no credentialed CORS (the API uses the `Authorization` header, not cookies) | `app/__init__.py` |
| Headers / errors | `nosniff`, `X-Frame-Options: DENY`, `no-store`, CSP `default-src 'none'`, HSTS in production; internal exceptions are logged, clients get generic messages | `app/__init__.py`, `security.server_error` |
| SQL injection | Table/column names are validated as plain identifiers; **filter keys must be mapped columns** (previously any string was spliced into SQL); `LIMIT`/`OFFSET` are clamped integers; values are always bound | `schema/query_builder.py` |
| Ownership integrity | The owner-scope stamp on create is authoritative (a caller/LLM can no longer set another owner's id); MySQL create now actually persists it (it was silently dropped) | `data_manager.py`, `mysql_driver.py` |
| SSRF / credential exfiltration | Salesforce `instance_url` must be https on a Salesforce domain, Dynamics `dynamics_url` on a Dynamics domain, `tenant_id` is validated; optional `BLOCK_PRIVATE_CONNECTOR_HOSTS` rejects DB hosts that resolve to private/loopback addresses | `security.py`, drivers |
| LiveKit | Room name is always server-generated (128-bit random) and a client-supplied `room` is ignored; token TTL 1 h; display name length-limited | `routes/livekit.py` |
| Inputs | E-mail format, role allow-list, password length (8–72 bytes), connector type allow-list, pagination clamping, 1 MB body limit, malformed UUID → 400 | `security.py`, routes |
| Default credentials | Removed the seeded `admin@…` account (and its password in a comment) from `init_db.sql`; accounts are created with `manage.py` (password prompted) | `init_db.sql`, `manage.py` |
| Supply chain | Dependabot, `pip-audit`, `npm audit`, dependency review, gitleaks, CodeQL in CI | `.github/`, `docs/CI_CD.md` |

## Known limitations / residual risk (not fixed, with reason)

1. **Existing deployments must act.** Anyone who ran the old `init_db.sql` has a known admin password and possibly
   plaintext connector credentials. Change that password, set `CONNECTOR_ENCRYPTION_KEY`, run `manage.py
   encrypt-connectors`, and **rotate every credential that was ever stored or returned by the old API** (the old
   `GET /organizations/<id>` leaked them to any logged-in user).
2. **Permissive data-isolation default.** `allow_unowned_read` defaults to `True` and `restrict_to_owned_entities` to
   `False`: on the first read, a user of a tenant without an owner column sees all rows and *claims ownership of them*.
   Changing the default would change behaviour for existing tenants, so it is documented rather than altered.
   Recommended: set `restrict_to_owned_entities: true` for new tenants.
3. **`admin`/`owner` are global.** An `admin` can manage every organization and user (the dashboard lists all). There
   is no per-tenant admin concept beyond `PATCH /organizations/<own id>/connector` for `owner`s. Treat `admin` as
   platform staff.
4. **JWTs cannot be revoked** before expiry, and the web app keeps the token in `localStorage` (XSS exposure). Moving
   to short-lived access + refresh tokens in `httpOnly` cookies is a larger change (needs CSRF protection).
5. **Rate limiting is in-process** by default (`memory://`); with several gunicorn workers the effective limit is
   multiplied. Use `RATELIMIT_STORAGE_URI=redis://…` in production.
6. **Connector hosts are tenant-controlled.** Without `BLOCK_PRIVATE_CONNECTOR_HOSTS` an org admin can point Lia at an
   internal address. It is off by default because internal databases are a legitimate setup; enable it for SaaS.
   (A DNS-rebinding race between validation and connection remains possible.)
7. **LLM exposure.** Schema names and CRM content flow into prompts and tool results; a malicious record can try to
   steer the agent. Mitigations are structural (mapped columns only, owner scope, ownership checks), not prompt
   based. Tool error strings are returned to the model and may reach the user verbatim.
8. **Salesforce/Dynamics scope only through `owned_entity_ids`** (they ignore the owner-scope attributes), and the
   Dynamics driver follows `@odata.nextLink` URLs from Microsoft's response with the bearer token attached.
9. `verify_ssl: false` can still be set per connector (logged as a warning).
10. `mobile/android/app/debug.keystore` is the standard public React-Native debug key and is committed; never use it
    to sign releases.
11. Schema is still created with `db.create_all()` at startup (no migrations): see technical debt in
    `docs/REVIEW_REPORT.md`.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository (Security → Report a vulnerability); do not file a public
issue.
