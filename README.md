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
![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)

## Table of Contents
------------------
- [Project Demo Video](#project-demo-video) • [🚀 Project Overview](#-project-overview) • [📥 Setup Guide](#setup-guide) • [📖 How to Use](#-how-to-use) • [💡 Optimizations](#-optimizations) • [License](#license)

## Project Demo Video
------------------------------
<video src="assets/Lia.mp4" controls muted playsinline></video>

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
2. Create your environment file:

```bash
cp .env.docker .env
```

3. Open `.env` and configure required values:

```env
JWT_SECRET_KEY=your_secret_key_change_this
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
OPENAI_API_KEY=your_openai_api_key
```

4. Build and run all services:

```bash
make build
make up
```

5. Check running services:

```bash
make ps
```

#### Option B: Local development setup

Backend:

```bash
cd backend
python -m venv myenv
source myenv/bin/activate
pip install -r requirements.txt
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
- API Docs: `http://localhost:5000/api/docs`

## 📖 How to Use

### Admin flow (step-by-step)

1. Open the frontend at `http://localhost:3000` and log in as admin.
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

## 💡 Optimizations

- Add connector health monitoring with per-tenant status dashboards.
- Introduce retry queues and dead-letter handling for external CRM/API failures.
- Add tenant-level analytics (usage, latency, success rate, token cost).
- Expand RBAC and audit logs for enterprise governance.
- Add end-to-end integration tests per connector to reduce regression risk.
- Improve onboarding with guided setup validation for new organizations.

## License

This project is licensed under the [MIT License](LICENSE).
