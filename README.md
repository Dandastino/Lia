# Lia - Your AI Assistant

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
| **PostgreSQL** | External Database | `{host, port, database, user, password}` |
| **MySQL** | External Database | `{host, port, database, user, password}` |
| **HubSpot** | CRM | `{api_key}` |
| **Salesforce** | CRM | `{instance_url, client_id, client_secret, username, password}` |
| **Dynamics 365** | CRM | `{tenant_id, client_id, client_secret, dynamics_url}` |

## Project Structure

```
LIA_FOR_ALL/
├── backend/
│   ├── agent.py              # LiveKit voice agent entrypoint
│   ├── server.py             # Flask API server
│   ├── db_driver.py          # SQLAlchemy models (organizations, users, sync_logs)
│   ├── data_manager.py       # Router for connectors
│   ├── api_tools.py          # Generic agent tools (save_meeting, get_history)
│   ├── prompts.py            # System prompt builder
│   ├── requirements.txt      # Python dependencies
│   └── drivers/
│       ├── base.py           # Abstract driver interface
│       ├── postgresql_driver.py
│       ├── mysql_driver.py
│       ├── hubspot_driver.py
│       ├── salesforce_driver.py
│       └── dynamics_driver.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Login.jsx
│   │   │   ├── ConnectorSettings.jsx  # Configure org connector
│   │   │   ├── PatientDetail.jsx      # View client details
│   │   │   └── VoiceInterface.jsx     # Voice interaction UI
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## Setup Guide

### Prerequisites

- Python 3.10+
- Node.js 16+
- PostgreSQL (for Lia's internal database)
- LiveKit account (for voice functionality)

### Backend Setup

1. **Create a Python virtual environment:**
   ```bash
   cd backend
   python -m venv myenv
   source myenv/bin/activate  # On Windows: myenv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables (.env):**
   ```bash
   # Lia's internal database (stores organizations, users, sync logs)
   DB_USER=your_postgres_user
   DB_PASSWORD=your_postgres_password
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=lia_db
   
   # JWT authentication
   JWT_SECRET_KEY=your_secret_key_change_this
   
   # LiveKit (for voice)
   LIVEKIT_URL=ws://localhost:7880
   LIVEKIT_API_KEY=your_livekit_api_key
   LIVEKIT_API_SECRET=your_livekit_api_secret
   
   # OpenAI (for LLM)
   OPENAI_API_KEY=your_openai_api_key
   ```

4. **Initialize the database:**
   ```bash
   psql -U your_postgres_user -d lia_db -f init_db.sql
   ```
   (Create `init_db.sql` with the schema from the Quick Start section below)

5. **Start the Flask API:**
   ```bash
   python server.py
   ```

### Frontend Setup

1. **Install dependencies:**
   ```bash
   cd frontend
   npm install
   ```

2. **Start dev server:**
   ```bash
   npm run dev
   ```

3. **Build for production:**
   ```bash
   npm run build
   ```

## Quick Start

### 1. Create an Organization

```bash
curl -X POST http://localhost:5000/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@company.com",
    "password": "password123",
    "org_name": "Acme Corp",
    "org_industry": "sales"
  }'
```

Get the JWT token from response and the `org_id`.

### 2. Configure a Connector

Set up where the organization's data will be stored:

**For PostgreSQL:**
```bash
curl -X PATCH http://localhost:5000/organizations/{org_id}/connector \
  -H "Authorization: Bearer {jwt_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "connector_type": "postgresql",
    "connector_config": {
      "host": "client-db.example.com",
      "port": 5432,
      "database": "client_data",
      "user": "lia_user",
      "password": "secure_pass"
    }
  }'
```

**For HubSpot:**
```bash
curl -X PATCH http://localhost:5000/organizations/{org_id}/connector \
  -H "Authorization: Bearer {jwt_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "connector_type": "hubspot",
    "connector_config": {
      "api_key": "your_hubspot_api_key"
    }
  }'
```

### 3. Create Users for the Organization

```bash
curl -X POST http://localhost:5000/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@company.com",
    "password": "password123",
    "org_id": "{org_id}"
  }'
```

### 4. Start Using Lia

Users from the organization can now:
- Use the web UI to login
- Start voice consultations with Lia
- Lia automatically saves meetings to their configured system
- Lia retrieves meeting history from their system

## Database Schema (Lia's Internal DB)

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Organizations: Connector configuration
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    connector_type VARCHAR(50) NOT NULL,
    connector_config JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Users: Authentication
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Sync Logs: Audit trail
CREATE TABLE sync_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID REFERENCES organizations(id),
    status VARCHAR(50),
    target_system VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

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

## Environment Variables Explained

| Variable | Purpose |
|----------|---------|
| `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` | Lia's internal Postgres database |
| `JWT_SECRET_KEY` | Sign authentication tokens |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Voice meeting infrastructure |
| `OPENAI_API_KEY` | LLM for Lia's intelligence |

## API Endpoints

### Authentication
- `POST /register` - Create a new user/organization
- `POST /login` - Login user

### Organizations
- `PATCH /organizations/{org_id}/connector` - Configure connector for organization

## Development

### Adding a New Connector

1. Create `drivers/your_connector_driver.py`:
   ```python
   from .base import BaseDriver
   
   class YourConnectorDriver(BaseDriver):
       def __init__(self, connector_config):
           super().__init__(connector_config)
           # Initialize connection
       
       def save_meeting(self, user_id, payload):
           # Implement save logic
           return result
       
       def get_meeting_history(self, user_id, filters=None):
           # Implement retrieval logic
           return meetings
   ```

2. Update `data_manager.py`:
   ```python
   from drivers.your_connector_driver import YourConnectorDriver
   
   # In from_user_id():
   elif connector_type == "your_connector":
       driver = YourConnectorDriver(config)
   ```

3. Add dependencies to `requirements.txt` if needed

## Troubleshooting

### "Connector failed to connect"
- Verify credentials in `connector_config`
- Check database/API access from server

### "User not found"
- Ensure user is created under the correct organization
- Check `org_id` is set correctly

### "Meeting not saved"
- Check `sync_logs` table for error details
- Verify connector credentials

## Contributing

1. Create a feature branch
2. Make changes
3. Test with your organization's connector
4. Submit PR

## License

MIT

## Support

For issues or questions, please open a GitHub issue.
