# Lia Medical Assistant

An AI-powered medical assistant for home doctors providing 24-hour house call services. Lia helps doctors manage patient records, track medical history, and conduct voice-based consultations using AI.

## Features

### Doctor Features
- **Secure Authentication**: Login/Register system for doctors
- **Patient Management**: Create, view, update, and manage patient records
- **Medical History**: Complete medical history tracking for each patient
- **Session Management**: Track all consultation sessions with detailed notes
- **Patient Notes**: Add quick notes and observations to patient records
- **Voice Assistant**: AI-powered voice assistant (Lia) to help during consultations

### AI Assistant (Lia) Capabilities
- Lookup and retrieve patient medical history
- Remind doctors about patient problems and previous visits
- Create new patient records
- Update patient information
- Document session findings and diagnosis
- Add notes to patient records
- Real-time voice interaction during consultations

## Tech Stack

### Backend
- **Python 3.9+**
- **Flask**: Web framework
- **SQLAlchemy**: Database ORM
- **LiveKit**: Real-time audio/video
- **OpenAI**: AI language model
- **JWT**: Authentication
- **SQLite**: Database (can be changed to PostgreSQL/MySQL)

### Frontend
- **React 18**: UI framework
- **Vite**: Build tool
- **LiveKit Components**: Real-time communication
- **Axios**: HTTP client

## Installation & Setup

### Prerequisites
- Python 3.9 or higher
- Node.js 18 or higher
- LiveKit server (local or cloud)
- OpenAI API key

### Backend Setup

1. Navigate to the backend directory:
```powershell
cd backend
```

2. Create and activate a virtual environment:
```powershell
python -m venv myenv
.\myenv\Scripts\activate
```

3. Install dependencies:
```powershell
pip install -r requirements.txt
```

4. Create a `.env` file (copy from `.env.example`):
```powershell
cp .env.example .env
```

5. Configure your `.env` file with:
   - `LIVEKIT_API_KEY`: Your LiveKit API key
   - `LIVEKIT_API_SECRET`: Your LiveKit API secret
   - `LIVEKIT_URL`: Your LiveKit server URL
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `JWT_SECRET_KEY`: A secure random string

6. Start the Flask server:
```powershell
python server.py
```

The backend will run on `http://localhost:5001`

### Frontend Setup

1. Navigate to the frontend directory:
```powershell
cd frontend
```

2. Install dependencies:
```powershell
npm install
```

3. Create a `.env` file (copy from `sample.env`):
```powershell
cp sample.env .env
```

4. Configure your `.env` file with:
   - `VITE_LIVEKIT_URL`: Your LiveKit server URL (e.g., `ws://localhost:7880`)
   - `VITE_API_URL`: Backend API URL (e.g., `http://localhost:5001`)

5. Start the development server:
```powershell
npm run dev
```

The frontend will run on `http://localhost:5173`

### Running the AI Agent

1. Navigate to the backend directory and activate virtual environment
2. Run the LiveKit agent:
```powershell
python agent.py dev
```

## Usage Guide

### First Time Setup

1. **Start Backend Server**: `python server.py`
2. **Start AI Agent**: `python agent.py dev`
3. **Start Frontend**: `npm run dev`

### Using the Application

#### 1. Doctor Registration/Login
- Open the app at `http://localhost:5173`
- Register as a new doctor or login with existing credentials

#### 2. Managing Patients
- **View All Patients**: Dashboard shows all your patients
- **Create New Patient**: Click "+ New Patient" button
- **View Patient Details**: Click on any patient card

#### 3. Starting a Consultation
- Click "Start Consultation" button on patient detail page
- The AI assistant (Lia) will help you during the consultation

## API Endpoints

### Authentication
- `POST /register`: Register a new doctor
- `POST /login`: Doctor login

### Patients
- `GET /patients`: Get all patients
- `GET /patients/:id`: Get patient details
- `POST /patients`: Create new patient
- `PUT /patients/:id`: Update patient
- `DELETE /patients/:id`: Delete patient

### Sessions
- `POST /patients/:id/sessions`: Create new session
- `PUT /sessions/:id`: Update session

### Notes
- `POST /patients/:id/notes`: Add patient note

## Support

For issues and questions, please check the documentation.
