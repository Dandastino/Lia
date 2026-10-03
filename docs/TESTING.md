# Testing

## Layout

| Path | What it covers |
|------|----------------|
| `backend/tests/unit/` | Pure logic: config validation, security helpers, encryption, SQL query builder, FK resolver, schema mapper (LLM faked), inspector (SQLite) |
| `backend/tests/integration/` | Flask API end-to-end through the test client (auth, tenant isolation, admin, organizations, meetings, entities, LiveKit), `DataManager`, agent tool layer, models |
| `backend/tests/integration/providers/` | HubSpot, Salesforce and Dynamics drivers; every outbound HTTP call mocked with `responses` |
| `backend/tests/integration/test_sql_drivers_real_db.py` | PostgreSQL and MySQL drivers against **real servers** (same scenarios on both) |
| `frontend/src/**/*.test.jsx` | Vitest + Testing Library component tests (API and LiveKit mocked) |
| `frontend/e2e/` | Playwright user flows on Chromium against `vite preview`, API mocked with `page.route` |

The default backend suite needs no services: the Flask app runs on in-memory SQLite (`GUID` and `EncryptedJSON`
column types are dialect independent). Tests that need a real server are skipped unless their URL is set.

## Running

```bash
cd backend
pip install -r requirements-dev.txt
pytest --cov=app                      # SQLite only; real-DB tests are skipped

# real PostgreSQL + MySQL (example with throw-away containers)
docker run -d --name lia-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=lia_test -p 5432:5432 postgres:15-alpine
docker run -d --name lia-my -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=lia_test -p 3306:3306 mysql:8
export POSTGRES_TEST_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/lia_test
export MYSQL_TEST_URL=mysql+pymysql://root:root@localhost:3306/lia_test
pytest --cov=app

cd ../frontend
npm ci && npm test && npm run test:coverage && npx playwright install chromium && npm run test:e2e
```

The coverage gate is 85 % for the backend (CI runs with both databases and sits around 93 %) and 80/75/80/80
(statements/branches/functions/lines) for the frontend.

## Conventions

* **Security regressions are tests.** Examples: `test_every_admin_route_rejects_members` walks the URL map so a new
  `/admin` route cannot ship without an authorization check; reset-password-then-login pins the bcrypt/werkzeug bug;
  the query-builder tests feed SQL-injection payloads through filter keys, limits and values.
* Do not weaken a test to make it pass. If behaviour is wrong, fix the code and keep the test.
* A green run is not proof of absence of bugs: LLM behaviour (schema mapping quality, tool choice) and the real
  CRM APIs are only covered through mocks.

## Not covered (known gaps)

* `agent.py` (LiveKit worker entrypoint) and `prompts.py` are not exercised; they need a LiveKit/OpenAI sandbox.
* HubSpot/Salesforce/Dynamics are tested against mocks of the documented API, never against live tenants.
* Mobile app (`mobile/`) has no automated tests.
* Load/performance tests do not exist.
