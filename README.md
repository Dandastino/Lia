# 📊 Lia - Multi-Tenant AI Voice Assistant
-----------------------
*Lia helps teams manage meetings and customer data through natural voice interactions, while keeping each organization's data in its own CRM or database.*

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Build-Vite-646CFF?logo=vite&logoColor=white)
![LiveKit](https://img.shields.io/badge/Voice-LiveKit-07C160?logo=livekit&logoColor=white)
![OpenAI](https://img.shields.io/badge/LLM-OpenAI-412991?logo=openai&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Container-Docker-2496ED?logo=docker&logoColor=white)
![CI](https://github.com/Dandastino/Lia/actions/workflows/ci.yml/badge.svg)

• [📹 Project Demo Video](#project-demo-video) • [🚀 Project Overview](#-project-overview) • [📥 Setup Guide](#setup-guide) • [📖 How to Use](#-how-to-use) • [💡 Optimizations](#-optimizations) • [📃 License](#license)

## 📹 Project Demo Video

[Watch demo video (MP4)](assets/Lia.mp4)

------------------------------
## 🚀 Project Overview

Lia is a multi-tenant AI assistant designed for organizations that need a voice-first workflow to manage meetings, notes, and customer records.

### What it is

- A backend + frontend platform where users can speak naturally to an AI assistant.
- A multi-connector system that can route data operations to external databases and CRMs.
- A tenant-isolated architecture where each organization uses its own connector configuration and data source.

### Why it is useful

- Reduces manual meeting documentation.
- Improves information retrieval speed during and after meetings.
- Lets teams work with the tools they already use (PostgreSQL, MySQL, HubSpot, Salesforce, Dynamics).

### What problem it solves

- Scattered meeting notes and inconsistent follow-up.
- Slow data lookup across CRM/database systems.
- High operational friction when switching between communication and data-entry tools.

### Who it is built for

- Sales teams handling frequent client calls.
- Operations teams tracking meeting outcomes.
- Multi-tenant SaaS deployments where every organization must keep data in its own infrastructure.

### Architecture (high-level)

```text
User (Organization A)
   ↓
Lia Voice Agent
   ↓
DataManager (tenant-aware router)
   ↓
Connector Driver (PostgreSQL/MySQL/HubSpot/Salesforce/Dynamics)
   ↓
Organization-owned data system
```

Key principle: Lia orchestrates workflows and routing, while tenant data remains in tenant-owned systems.

### Supported connectors

| Connector | Type | Configuration |
|-----------|------|---------------|
| PostgreSQL | External Database | `{host, port, db_name, user, password}` |
| MySQL | External Database | `{host, port, db_name, user, password}` |
| HubSpot | CRM | `{api_key}` |
| Salesforce | CRM | `{client_id, client_secret, username, password}` |
| Dynamics 365 | CRM | `{tenant_id, client_id, client_secret}` |

## 📥 Setup Guide

### How to install

#### Prerequisites

- Docker and Docker Compose
- OpenAI API key
- LiveKit credentials (if voice features are enabled)

#### Option A: Docker setup (recommended)

1. Clone the repository and go to the root folder.
2. Create the environment files:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

3. Fill in the **required** secrets (the backend refuses to start without them):

```bash
# JWT signing key (>= 32 chars)
openssl rand -hex 32
# key that encrypts tenant connector credentials at rest
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put them in `JWT_SECRET_KEY` and `CONNECTOR_ENCRYPTION_KEY` (in both `.env` and `backend/.env`), and add your
`OPENAI_API_KEY` and `LIVEKIT_*` values. See [backend/.env.example](backend/.env.example) for every option.

4. Build and run all services:

```bash
make build
make up
```

5. Create the first organization and admin. **No default account is shipped**; the password is prompted:

```bash
docker compose exec backend python manage.py org create "My Company" --connector internal
docker compose exec backend python manage.py user create admin@example.com --org-id <org-uuid> --role admin
```

6. Check running services: `make ps`

#### Option B: Local development setup

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env             # then fill it in (see above)
python server.py
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

### How to configure

- Configure organization-level connector details in the Admin panel.
- Select the connector type per organization.
- Save API/database credentials for each tenant.
- Verify connection by creating or querying sample records.

Default local URLs:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5000`

## 📖 How to Use

### Admin flow (step-by-step)

1. Open the frontend at `http://localhost:3000` and log in with the admin you created with `manage.py`.
2. Go to the Administration area.
3. Create an organization and choose its connector type.
4. Enter connector credentials and save.
5. Create users and assign them to the organization.
6. Test with a first voice meeting to confirm end-to-end sync.

### End-user flow (step-by-step)

1. Log in with your user account.
2. Open the voice interface.
3. Start a conversation naturally with Lia.
4. Ask Lia to save meeting notes, retrieve history, or update customer details.
5. Confirm the data is persisted in your organization's configured system.

### Data flow example

```text
Voice input -> Lia processing -> tool call -> DataManager routing -> connector driver -> tenant system
```

## ✅ Running the checks

| What | Command |
|------|---------|
| Backend lint | `cd backend && ruff check .` |
| Backend tests + coverage (SQLite, no services needed) | `cd backend && pytest --cov=app` |
| Backend tests against real PostgreSQL/MySQL | set `POSTGRES_TEST_URL` / `MYSQL_TEST_URL` (see [docs/TESTING.md](docs/TESTING.md)) |
| Frontend lint / unit / build | `cd frontend && npm ci && npm run lint && npm run test:coverage && npm run build` |
| Frontend end-to-end | `cd frontend && npm run test:e2e` |
| Mobile lint / tests | `cd mobile && npm ci && npm run lint && npm run test:coverage` |

Every pull request runs the same checks in CI; see [docs/CI_CD.md](docs/CI_CD.md).

## 🔐 Security & privacy

- Security model, hardening done and known limitations: [docs/SECURITY.md](docs/SECURITY.md)
- Personal-data inventory and GDPR gap analysis: [docs/GDPR.md](docs/GDPR.md)
- Full review report (findings, fixes, remaining debt): [docs/REVIEW_REPORT.md](docs/REVIEW_REPORT.md)

## 💡 Optimizations

- Add connector health monitoring with per-tenant status dashboards.
- Introduce retry queues and dead-letter handling for external CRM/API failures.
- Add tenant-level analytics (usage, latency, success rate, token cost).
- Expand RBAC and audit logs for enterprise governance.
- Add end-to-end integration tests per connector to reduce regression risk.
- Improve onboarding with guided setup validation for new organizations.

## 📃 License

This project is licensed under the [MIT License](LICENSE).
