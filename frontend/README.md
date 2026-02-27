# Lia Frontend

React + Vite frontend for Lia AI Assistant. Provides user authentication, connector configuration, and voice interface.

## Components

- **Login.jsx** - User authentication
- **ConnectorSettings.jsx** - Configure organization's data connector (PostgreSQL, MySQL, HubSpot, etc.)
- **VoiceInterface.jsx** - Real-time voice conversation with Lia
- **PatientDetail.jsx** - View/manage client details (industry-specific)

## Setup

```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# Build for production
npm run build
```

## Environment Variables (.env)

```bash
VITE_API_URL=http://localhost:5000
```

## Development

The frontend connects to the Flask backend at `http://localhost:5000`.

Make sure the backend is running before starting the frontend:

```bash
# Terminal 1: Backend
cd backend
source myenv/bin/activate
python server.py

# Terminal 2: Frontend
cd frontend
npm run dev
```

## Features

- **Multi-tenant UI** - Register and manage organizations
- **Connector Configuration** - Easy setup for different data systems
- **Voice Interface** - Real-time audio input/output with Lia
- **Session Management** - JWT token-based authentication
- **Responsive Design** - Works on desktop and tablet

## API Integration

The frontend uses the following endpoints:

### Authentication
- `POST /register` - Create new user/organization
- `POST /login` - Login

### Organizations
- `PATCH /organizations/{org_id}/connector` - Update connector config

All requests include JWT token in the `Authorization` header.

## Browser Support

- Chrome (recommended)
- Safari
- Edge
- Firefox

## Troubleshooting

### "Cannot connect to backend"
- Ensure Flask server is running on `localhost:5000`
- Check `VITE_API_URL` environment variable

### "Audio not working"
- Check browser microphone permissions
- Ensure WebRTC is enabled
- Try using HTTPS (required for some browsers)
