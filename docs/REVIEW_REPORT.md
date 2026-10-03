# Lia – full project review

Branch `chore/full-review`. Scope: discovery → audit (UI/UX, CI/CD, testing/quality, security/GDPR) → prioritisation →
implementation → verification. Behaviour changes are listed explicitly in §11.

## 1. Project overview

Lia is a multi-tenant AI voice assistant. A LiveKit/OpenAI agent calls tools; tools go through `DataManager`, which
selects a connector driver (PostgreSQL, MySQL, HubSpot, Salesforce, Dynamics) per organization. Business data stays in
the tenant's system; Lia's own PostgreSQL holds organizations, users, ownership links, CRM identity mappings and sync
logs.

| Component | Tech | Notes |
|-----------|------|-------|
| API | Flask 3, SQLAlchemy 2, flask-jwt-extended, gunicorn | `backend/app` |
| Voice agent | livekit-agents + OpenAI Realtime | `backend/agent.py` |
| Web | React 18 + Vite (+ LiveKit components) | `frontend/` |
| Mobile | Expo / React Native | `mobile/` (untested, only touched for the masked-secret edge) |
| Deploy | Docker Compose (dev/prod), nginx | `docker-compose*.yml`, `nginx.prod.conf` |

## 2. Architecture analysis

Request → JWT → route → `DataManager.from_user_id` → driver. SQL drivers are schema-agnostic: an LLM maps a
tenant's tables to normalised entities once (`schema/mapper.py`, validated against the introspected schema), the
mapping is stored in `connector_config.schema_mappings`, and `DynamicQueryBuilder` builds SQL from it. Ownership is
enforced by (a) an owner column resolved per user and (b) `user_entity_ownership` links.

Strengths: clean driver interface, ownership checks on update/delete, mapping validated against real schema, parameter
binding for values. Weaknesses: see §12.

## 3. Problems found (prioritised)

Severity = technical impact × exploitability, not effort.

### Critical

| ID | Problem | Cause | Impact | Fix | Verified by |
|----|---------|-------|--------|-----|-------------|
| C1 | Any logged-in user could read **any** tenant's connector credentials (`GET /organizations/<id>`) | No tenant check, config returned in clear | Full takeover of other tenants' CRM/DB | Membership check (404 otherwise), config only for admins and masked; echo-back merge | `test_organizations_api.py` |
| C2 | Known admin credential seeded by `init_db.sql` (password in a comment) | Convenience seed | Admin takeover on any deployment using the file | Seed removed; `manage.py` prompts for password | file diff; README flow |
| C3 | Connector credentials stored in plaintext JSONB | No encryption | DB dump = all tenant secrets | Fernet `EncryptedJSON` column, rotation, `encrypt-connectors` | `test_crypto.py` (raw SQL shows no plaintext) |
| C4 | Dynamic SQL: **filter keys** (LLM/client controlled) and `LIMIT` were spliced into SQL text | f-string building in `DynamicQueryBuilder` | SQL injection through prompt injection / `GET /entities?...` | Identifier allow-list, filter keys must be mapped columns, clamped ints | `test_query_builder.py`, real-DB injection tests on PG + MySQL |

### High

| ID | Problem | Fix |
|----|---------|-----|
| H1 | Weak default `JWT_SECRET_KEY` in compose, no startup validation | Required secret, production strength check |
| H2 | CORS `*` with credentials (also reflected in nginx) | Allow-list; nginx no longer reflects origin |
| H3 | No login rate limit, user enumeration ("Email does not exist"), timing differences | flask-limiter + nginx zone, uniform error, dummy hash |
| H4 | `str(e)` returned to clients in ~40 places (also `/health`) | `server_error()` logs and returns generic message |
| H5 | `GET /organizations` public | Auth required, scoped |
| H6 | `/getToken` accepted client-chosen `room` (join others' rooms) | Server-generated 128-bit room, TTL 1 h |
| H7 | **Admin password reset locked users out** (werkzeug hash vs bcrypt verify) | Use `User.set_password` (regression test) |
| H8 | **MySQL `create_entity` silently dropped the owner stamp and resolved foreign keys** (SQL built before enrichment) | Rebuild INSERT; found by the real-DB tests |
| H9 | Caller could set the owner column on create (ownership spoofing via `fields`/`metadata`/HTTP body) | Owner stamp is authoritative |
| H10 | SSRF/credential exfiltration through tenant-set `instance_url` (Salesforce posts client secret + password), `dynamics_url`, `tenant_id` in URL | Domain allow-lists; optional private-host block for DB hosts |
| H11 | `entity_id` placed raw in Salesforce/Dynamics URL paths; owned ids unencoded in OData `$filter` | Percent-encoding (found by driver tests) |
| H12 | `participants` column typed as `postgresql.UUID` (import alias `UUID as JSONB`) in the PG legacy meeting model | Real `JSONB` |
| H13 | `frontend/src/lib/` was **git-ignored** by the Python `lib/` rule → a fresh clone could not build | `!src/lib/` + files committed |
| H14 | No tests, no CI | See §6/§7 |

### Medium / Low (all fixed unless listed in §12)

Unvalidated e-mail/role/password/pagination input; emails not normalised on create (could not log in); admin could
delete/demote themselves; schema drift between `init_db.sql` and models (`external_email`, `last_synced_at`); Makefile
targets pointing at missing files; Node 18 / `npm install --legacy-peer-deps` Dockerfile; committed `mobile/build.log`
and an empty root `package-lock.json`; `console.log` of tokens in the web app; unguarded `JSON.parse(localStorage)`;
mobile org edit wiped connector config; sync-log messages unbounded; 20+ lint findings (unused code, missing
`raise … from`, `zip` strictness) fixed.

## 4. UI/UX audit

Full detail in [frontend/docs/UI_UX_AUDIT.md](../frontend/docs/UI_UX_AUDIT.md). Highlights: no design tokens/inconsistent
styles; non-semantic controls and missing labels/focus states; no loading/empty/error states, destructive actions
without confirmation; token and user objects logged to the console; 900-line `Admin.jsx`; no error boundary; no 401
handling; secrets round-tripped through forms. Implemented: token-based design system with AA contrast, focus-visible
and reduced-motion, semantic landmarks + skip link, accessible dialogs, inline validation, loading/empty/error
states, `ErrorBoundary`, central API helper with 401 logout, `Admin` split into components, lazy-loaded voice view
(main bundle 633 kB → 232 kB). Not done: URL-based navigation (still `useState`), httpOnly-cookie session, axe-core
scan, visual review by a human.

## 5. Testing audit

Before: **zero** tests; Makefile referenced non-existent ones. Difficult-to-test areas: module-level `create_app()` in
`manage.py`, config evaluated at import, PostgreSQL-only column types, LLM calls inside services.

## 6. Tests added

| Suite | Count | Notes |
|-------|-------|-------|
| Backend unit | 177 | config, security helpers, crypto, query builder (incl. injection payloads), FK resolver, mapper (LLM faked), inspector |
| Backend integration (API/service/tools) | 191 | auth, rate limit, CORS/headers, GDPR endpoints, admin (URL-map walk proves every `/admin` route rejects members), organizations/IDOR, meetings/entities/LiveKit, DataManager modes + owner resolution, agent tools, models |
| Provider integration (mocked HTTP) | 445 | HubSpot, Salesforce, Dynamics: OAuth/401 retry, CRUD, schema, SOQL/OData escaping, owner/ownership |
| Real database integration | 36 (18 × PostgreSQL 15, MySQL 8) | same scenarios on both: CRUD, owner isolation, FK name resolution, injection attempts, legacy meetings |
| Frontend unit/component | 81 | 93 % statements / 89 % branches |
| Frontend E2E (Playwright) | 16 | login, roles, session expiry, admin CRUD with confirm dialog, keyboard/a11y smoke, mobile viewport |

Backend total: **849 tests, 93 % line+branch coverage** with both databases (815 passed / 34 skipped, 87 %+ without
them); gate 85 %. Per module: drivers 88–99 %, `data_manager` 86 %, routes 85–100 %, `security`/`config`/`utils`
~100 %. Details and how to run: [TESTING.md](TESTING.md).

## 7. CI/CD audit and implementation

Before: no `.github`, no checks. Added (see [CI_CD.md](CI_CD.md)): one workflow with backend lint, backend tests
(PostgreSQL + MySQL service containers, coverage gate), frontend lint/unit/build, Playwright E2E, `pip-audit`, `npm
audit`, gitleaks, Docker builds, and an aggregator job `ci-passed` to be the single required check; CodeQL;
dependency review; Dependabot (pip, npm ×2, actions, docker); CODEOWNERS; PR/issue templates; labeler; PR-title
check; and `.github/scripts/apply-branch-protection.sh` (dry-run capable). **Branch protection has NOT been applied**:
it is a repository setting the owner must enable after the first CI run (steps in CI_CD.md). Workflows have not run on
GitHub yet; they were validated for YAML syntax only.

## 8. Code quality audit

Ruff (`E,F,W,I,B,UP,S,C90`) now passes on `backend/`. Remaining structural smells, deliberately not refactored
(risk > benefit without a live tenant): `hubspot_driver.py` (1.4k lines), `data_manager.py` (900 lines;
`_resolve_external_owner_id` complexity 30), duplicated SQL logic between the PG and MySQL drivers, drivers
authenticating in constructors (an OAuth call per `from_user_id`), `DataManager` mutating a driver with per-request
attributes (`request_owner_*`; not safe if a driver instance were shared across requests).

## 9. Security audit

See [SECURITY.md](SECURITY.md) for controls and residual risks. Secret scan of the working tree: no real secrets found
beyond the seeded admin password (removed from the file; still in git history) and the public Android debug keystore.
`pip-audit` and `npm audit`: no known vulnerabilities at the time of the run (not proof of safety).

## 10. GDPR / privacy audit

See [GDPR.md](GDPR.md): data inventory, third-party flows, gap table and the organisational questions that cannot be
answered from code. Added `GET /me/export`, `DELETE /me`, `PUT /me/password`, `purge-sync-logs`.

## 11. Changes implemented (behaviour changes to know about)

* App refuses to start without `JWT_SECRET_KEY`; in production also without a strong key and explicit `CORS_ORIGINS`.
  `CONNECTOR_ENCRYPTION_KEY` is required by the production compose file.
* `GET /organizations` and `/organizations/<id>` need auth/membership; connector secrets are masked (`********`).
* Login: wrong credentials always `401 Invalid email or password`; user without org `403` (was 401); rate limited.
* JWT lifetime default 8 h (was 24 h, configurable). Room names are server-generated.
* Admin cannot delete themselves or drop their own admin role; roles/connector types are allow-listed; passwords ≥ 8.
* Query filters naming unknown columns now fail with a clear error (they used to produce a SQL error or worse).
* `init_db.sql` no longer seeds an admin; use `manage.py`.
* New endpoints: `GET /me/export`, `DELETE /me`, `PUT /me/password`.
* `react-router-dom` removed from the frontend (unused); `Admin`/forms restyled and split.
* `.gitignore`: `lib/` rule no longer hides `frontend/src/lib`.

## 12. Remaining issues and technical debt

1. No DB migrations (`create_all()` at start, plus a legacy column back-fill in `models.py`): introduce Alembic.
2. Permissive tenant read defaults and global `admin` role (SECURITY.md §2–3).
3. Token in `localStorage`, no revocation/refresh; in-memory rate-limit store.
4. Large modules/duplicated SQL driver logic (§8); HubSpot `limit` unclamped; Salesforce/Dynamics ignore owner scope.
5. `agent.py`, `prompts.py`, mobile app untested; no load tests; no audit log of admin actions.
6. `three`, `@react-three/*`, `@readyplayerme/visage` are unused in the web app (left in `package.json`).
7. Git history still contains the old seeded admin password: rotate it; rewrite history only if desired.
8. Navigation without URLs; no i18n; UI not visually reviewed by a human.
9. The Docker images build, but the full compose stack (agent + LiveKit + OpenAI) was not run end to end.

## 13. Recommendations

Priority order: (1) rotate any credentials previously stored/returned by the old API and set the encryption key;
(2) enable branch protection and secret scanning; (3) default new tenants to `restrict_to_owned_entities`;
(4) Alembic migrations; (5) Redis rate-limit store and short-lived tokens in httpOnly cookies; (6) split the big
modules behind the new test net; (7) answer the GDPR open questions and publish a privacy notice.
