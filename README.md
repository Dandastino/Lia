# Lia - Your AI Assistant

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Build-Vite-646CFF?logo=vite&logoColor=white)
![LiveKit](https://img.shields.io/badge/Voice-LiveKit-07C160?logo=livekit&logoColor=white)
![OpenAI](https://img.shields.io/badge/LLM-OpenAI-412991?logo=openai&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Container-Docker-2496ED?logo=docker&logoColor=white)
![WebSocket](https://img.shields.io/badge/Protocol-WebSocket-010101?logo=socket.io&logoColor=white)
![REST API](https://img.shields.io/badge/API-REST-009688?logo=api&logoColor=white)
![JWT](https://img.shields.io/badge/Auth-JWT-000000?logo=jsonwebtokens&logoColor=white)
![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)

Lia is a multi-tenant AI voice assistant that helps professionals efficiently manage meetings, client information, and related records through natural conversation. Each organization connects Lia to their own data system (CRM or database), so customer data stays in their infrastructure.


## Architecture Overview

### Multi-Tenant Design

```
User (from Organization A)
    ↓
Lia Agent (processes voice)
    ↓
DataManager (routes based on org config)
    ↓
Connector Driver (PostgreSQL, HubSpot, Salesforce, etc.)
    ↓
Organization's Data System (their own database or CRM)
```

**Key principle:** Each organization stores their data in their own system. Lia is the orchestrator, not the data storage layer.

### Supported Connectors

| Connector | Type | Configuration |
|-----------|------|---|
| **PostgreSQL** | External Database | `{host, port, db_name, user, password}` |
| **MySQL** | External Database | `{host, port, db_name, user, password}` |
| **HubSpot** | CRM | `{api_key}` |
| **Salesforce** | CRM | `{client_id, client_secret, username, password}` |
| **Dynamics 365** | CRM | `{tenant_id, client_id, client_secret` |


## Setup Guide

### Prerequisites

- Docker & Docker Compose
- LiveKit account (for voice functionality)
- OpenAI API key (for LLM)

### Quick Start with Docker

1. **Clone and navigate to project:**
   ```bash
   cd LIA_FOR_ALL
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.docker .env
   ```
   Then edit `.env` with your credentials:
   ```bash
   # JWT authentication
   JWT_SECRET_KEY=your_secret_key_change_this
   
   # LiveKit (for voice)
   LIVEKIT_URL=ws://localhost:7880
   LIVEKIT_API_KEY=your_livekit_api_key
   LIVEKIT_API_SECRET=your_livekit_api_secret
   
   # OpenAI (for LLM)
   OPENAI_API_KEY=your_openai_api_key
   ```

3. **Build and start all services:**
   ```bash
   make build
   make up
   ```

4. **Verify services are running:**
   ```bash
   make ps
   ```

**Services will be available at:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:5000
- API Docs: http://localhost:5000/api/docs
- Database: localhost:5432

### Manual Setup 

If you prefer to run services locally without Docker:

**Backend:**
```bash
cd backend
python -m venv myenv
source myenv/bin/activate  # On Windows: .\myenv\Scripts\activate
pip install -r requirements.txt
python server.py
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## How to use Lia 

### Admin

**Access the Admin Panel:**
- Login at `http://localhost:3000` with admin account
- Navigate to the Administration Panel tab

**Create an Organization:**
1. Go to **Create Organization** tab
2. Fill in:
   - **Organization Name**: e.g., "Acme Corporation"
   - **Industry**: e.g., "Healthcare", "Finance"
   - **Connector Type**: Select from dropdown (PostgreSQL, MySQL, HubSpot, Salesforce, Dynamics)
3. Fill in connector credentials (database details or API keys)
4. Click **Create Organization**

**Manage Users:**
1. Go to **Manage Users** tab
2. Click **Edit** to modify user details or **Delete** to remove
3. Or go to **Create User** tab to add new users

**Edit Organization:**
1. Go to **Organizations** tab
2. Click **Edit** to modify connector configuration
3. Click **Save Organization**

### User

**Login and Access:**
- Go to `http://localhost:3000`
- Login with your email and password

**Use Voice Interface:**
- Speak naturally to Lia about meetings, clients, or information you need

**What Lia Can Do:**
- Save meeting summaries to your organization's system
- Retrieve meeting history and client information
- Update records in your connected CRM or database
- Provide context from your existing data


## How Data Flows

### Saving a Meeting

```
1. User speaks to Lia
2. Lia processes conversation → extracts meeting summary
3. Agent calls MiddlewareTools.save_meeting()
4. api_tools.py calls DataManager.save_meeting()
5. DataManager looks up user's organization
6. Reads org.connector_type and org.connector_config
7. Creates appropriate driver (PostgreSQLDriver, HubSpotDriver, etc.)
8. Driver saves meeting to organization's system
9. SyncLog entry created for audit
```

### Retrieving Meeting History

```
1. Model asks for meeting history via get_history tool
2. DataManager determines connector type
3. Driver queries organization's system
4. Results returned to Lia for context
```
