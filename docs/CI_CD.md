# CI/CD

All automation lives in `.github/`. No deploy target is defined here; the pipeline verifies, it does not deploy.

## Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci.yml` | PR to `main`, push to `main` | Lint, test, build, security scans |
| `codeql.yml` | PR, push to `main`, weekly | Static analysis (Python, JS/TS) |
| `dependency-review.yml` | PR | Blocks PRs adding high-severity vulnerable dependencies |
| `pr-labeler.yml` | PR | Adds `backend`/`frontend`/`mobile`/`ci`/`docs` labels (never checks out PR code) |
| `pr-title.yml` | PR | Conventional Commits title (`feat(backend): ...`) |

## Checks

| Check name | What it does | Required |
|---|---|---|
| `ci-passed` | Aggregates all jobs below (fails on failure/cancel/skip) | **Yes (the only one to require)** |
| `backend-lint` | `ruff check .` | via ci-passed |
| `backend-test` | pytest + coverage gate (70%), with postgres:15 and mysql:8 services | via ci-passed |
| `frontend-lint-test-build` | `npm ci`, lint, `test:coverage`, build | via ci-passed |
| `frontend-e2e` | Playwright (chromium) against the built app | via ci-passed |
| `security-pip-audit` | `pip-audit -r backend/requirements.txt` | via ci-passed |
| `security-npm-audit` | `npm audit --audit-level=high` | via ci-passed |
| `secret-scan` | gitleaks over full history | via ci-passed |
| `docker-build` | Builds backend and frontend images (no push) | via ci-passed |
| `codeql (python)`, `codeql (javascript-typescript)`, `dependency-review`, `semantic-title` | Separate workflows | Optional; add to required checks if desired |

Requiring only `ci-passed` keeps branch protection stable when jobs are added or renamed. To require the individual checks too, add their names above.

## Run checks locally

Backend (from `backend/`):

```bash
pip install -r requirements.txt -r requirements-dev.txt
ruff check .
pytest --cov=app --cov-report=term-missing --cov-fail-under=70
# optional real-DB tests:
export POSTGRES_TEST_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/lia_test
export MYSQL_TEST_URL=mysql+pymysql://root:root@localhost:3306/lia_test
pip install pip-audit && pip-audit -r requirements.txt
```

Frontend (from `frontend/`):

```bash
npm ci
npm run lint
npm run test:coverage
npm run build
npx playwright install chromium && npm run test:e2e
npm audit --audit-level=high
```

Other: `docker build -f backend/Dockerfile .`, `docker build -f frontend/Dockerfile .` (from repo root); `gitleaks detect --redact`.

## Enable branch protection

Script (needs repo admin and `gh auth login`):

```bash
.github/scripts/apply-branch-protection.sh --dry-run   # preview
.github/scripts/apply-branch-protection.sh             # apply
```

It requires: PR before merge, 1 approval, code-owner review, stale review dismissal, up-to-date branch with `ci-passed`, resolved conversations, linear history, no force pushes/deletions, enforced for admins. Run it after `ci.yml` has run once on `main` so the check name is known to GitHub.

Manual equivalent: Settings > Branches > Add branch protection rule for `main`, and enable each option listed above (status check: `ci-passed`).

## Repository settings the owner must toggle

- Settings > Code security: enable Dependency graph, Dependabot alerts, Dependabot security updates, Secret scanning and Push protection, and Code scanning (CodeQL workflow uploads results).
- Settings > Actions > General: workflow permissions "Read repository contents" by default.
- Create labels used by the labeler and Dependabot: `backend`, `frontend`, `mobile`, `ci`, `docs`, `dependencies`.

## Dependabot, CodeQL, secrets

- Dependabot opens weekly grouped minor/patch PRs for pip, npm (frontend, mobile), GitHub Actions and Docker. Major bumps arrive as separate PRs.
- CodeQL runs `security-extended` queries; findings appear under Security > Code scanning.
- If gitleaks flags a real secret: rotate it first, then remove it from history. For false positives add a `.gitleaks.toml` allowlist.

## Handling failures

1. Open the failed job log; reproduce locally with the commands above.
2. `backend-test` failing only on postgres/mysql: check the service healthcheck and the `*_TEST_URL` values.
3. `frontend-e2e`: download the `playwright-report` artifact (uploaded on failure).
4. Audit failures: upgrade the dependency; if no fix exists, document and suppress narrowly (e.g. `pip-audit --ignore-vuln ID`) with a tracking issue.
5. Coverage gate: add tests rather than lowering `BACKEND_COVERAGE_MIN` in `ci.yml`.

## Releases and versioning

Use SemVer with annotated tags (`vX.Y.Z`) on `main` and GitHub Releases with generated notes; Conventional Commit titles make the changelog derivable. Squash-merge so history stays linear.
