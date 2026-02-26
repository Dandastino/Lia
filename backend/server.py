import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from livekit import api
from dotenv import load_dotenv
from db_driver import db, DatabaseDriver
import uuid
from datetime import timedelta

load_dotenv()

app = Flask(__name__)


def build_postgres_uri():
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    host = os.getenv('DB_HOST')
    port = os.getenv('DB_PORT')
    dbname = os.getenv('DB_NAME')
    missing = [k for k, v in [('DB_USER', user), ('DB_PASSWORD', password), ('DB_HOST', host), ('DB_PORT', port), ('DB_NAME', dbname)] if not v]
    if missing:
        raise RuntimeError(f"Missing required environment variables for DB config: {', '.join(missing)}")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = build_postgres_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)

CORS(app, resources={r"/*": {"origins": "*"}})
jwt = JWTManager(app)

db_driver = DatabaseDriver()
db_driver.init_app(app)


def _serialize_patient(p):
    return {
        'id': str(p.id),
        'name': p.get_full_name(),
        'first_name': p.first_name,
        'last_name': p.last_name,
        'date_of_birth': p.date_of_birth.isoformat() if p.date_of_birth else None,
        'gender': p.gender,
        'contact_info': p.contact_info,
        'created_at': p.created_at.isoformat() if p.created_at else None,
    }


# ==================== AUTHENTICATION ROUTES ====================

@app.route("/register", methods=["POST"])
def register():
    """Register a new doctor"""
    try:
        data = request.get_json()

        # Accept first_name/last_name or full_name (split for backward compatibility)
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        if not first_name and data.get('full_name'):
            parts = data['full_name'].strip().split(None, 1)
            first_name = parts[0] if parts else ''
            last_name = parts[1] if len(parts) > 1 else ''
        if not data or not all(k in data for k in ['email', 'password']) or not first_name or not last_name:
            return jsonify({'error': 'Missing required fields (email, password, and full name or first_name + last_name)'}), 400

        existing_doctor = db_driver.get_doctor_by_email(data['email'])
        if existing_doctor:
            return jsonify({'error': 'Email already registered'}), 409

        doctor = db_driver.create_doctor(
            email=data['email'],
            password=data['password'],
            first_name=first_name,
            last_name=last_name,
            specialty=data.get('specialty')
        )

        if not doctor:
            return jsonify({'error': 'Failed to create doctor account'}), 500

        access_token = create_access_token(identity=str(doctor.id))

        return jsonify({
            'message': 'Doctor registered successfully',
            'access_token': access_token,
            'doctor': {
                'id': str(doctor.id),
                'email': doctor.email,
                'full_name': doctor.get_full_name(),
                'first_name': doctor.first_name,
                'last_name': doctor.last_name,
                'specialty': doctor.specialty,
                'specialization': doctor.specialty  # backward compat for frontend
            }
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/login", methods=["POST"])
def login():
    """Login a doctor"""
    try:
        data = request.get_json()

        if not data or not all(k in data for k in ['email', 'password']):
            return jsonify({'error': 'Missing email or password'}), 400

        doctor = db_driver.get_doctor_by_email(data['email'])

        if not doctor or not doctor.check_password(data['password']):
            return jsonify({'error': 'Invalid email or password'}), 401

        access_token = create_access_token(identity=str(doctor.id))

        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'doctor': {
                'id': str(doctor.id),
                'email': doctor.email,
                'full_name': doctor.get_full_name(),
                'first_name': doctor.first_name,
                'last_name': doctor.last_name,
                'specialty': doctor.specialty,
                'specialization': doctor.specialty  # backward compat for frontend
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== PATIENT MANAGEMENT ROUTES ====================

@app.route("/patients", methods=["GET"])
@jwt_required()
def get_all_patients():
    """Get all patients for the logged-in doctor"""
    try:
        doctor_id = get_jwt_identity()
        patients = db_driver.get_all_patients(doctor_id)

        patients_data = []
        for p in patients:
            last_apts = db_driver.get_patient_appointments(p.id, doctor_id, limit=1)
            last_updated = last_apts[0].appointment_date if last_apts else p.created_at
            patients_data.append({
                'id': str(p.id),
                'name': p.get_full_name(),
                'first_name': p.first_name,
                'last_name': p.last_name,
                'contact_info': p.contact_info,
                'created_at': p.created_at.isoformat() if p.created_at else None,
                'last_updated': last_updated.isoformat() if last_updated else None
            })

        return jsonify({
            'patients': patients_data,
            'total': len(patients_data)
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/patients/<patient_id>", methods=["GET"])
@jwt_required()
def get_patient(patient_id):
    """Get detailed patient information"""
    try:
        doctor_id = get_jwt_identity()
        patient = db_driver.get_patient_by_id(patient_id, doctor_id)

        if not patient:
            return jsonify({'error': 'Patient not found'}), 404

        appointments = db_driver.get_patient_appointments(patient_id, doctor_id, limit=5)
        appointments_data = []
        for a in appointments:
            appointments_data.append({
                'id': str(a.id),
                'date': a.appointment_date.isoformat() if a.appointment_date else None,
                'transcript': a.transcript,
                'ai_summary': a.ai_summary,
                'diagnoses': [{'condition_name': d.condition_name, 'is_chronic': d.is_chronic} for d in db_driver.get_diagnoses_for_appointment(a.id)],
                'prescriptions': [{'medication_name': p.medication_name, 'dosage': p.dosage, 'frequency': p.frequency} for p in db_driver.get_prescriptions_for_appointment(a.id)]
            })

        memories = db_driver.get_patient_memories(patient_id, limit=10)
        notes_data = [{
            'id': str(n.id),
            'content': n.content,
            'date': n.created_at.isoformat() if n.created_at else None
        } for n in memories]

        return jsonify({
            'patient': {
                **_serialize_patient(patient),
            },
            'appointments': appointments_data,
            'notes': notes_data
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/patients", methods=["POST"])
@jwt_required()
def create_patient():
    """Create a new patient"""
    try:
        doctor_id = get_jwt_identity()
        data = request.get_json()

        if not data or not all(k in data for k in ['first_name', 'last_name', 'date_of_birth']):
            return jsonify({'error': 'Missing required fields (first_name, last_name, date_of_birth)'}), 400

        patient = db_driver.create_patient(
            primary_doctor_id=doctor_id,
            first_name=data['first_name'],
            last_name=data['last_name'],
            date_of_birth=data['date_of_birth'],
            gender=data.get('gender'),
            contact_info=data.get('contact_info')
        )

        if not patient:
            return jsonify({'error': 'Failed to create patient'}), 500

        return jsonify({
            'message': 'Patient created successfully',
            'patient': {
                'id': str(patient.id),
                'name': patient.get_full_name(),
                'contact_info': patient.contact_info
            }
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/patients/<patient_id>", methods=["PUT"])
@jwt_required()
def update_patient(patient_id):
    """Update patient information"""
    try:
        doctor_id = get_jwt_identity()
        data = request.get_json()

        allowed = {'first_name', 'last_name', 'date_of_birth', 'gender', 'contact_info'}
        updates = {k: v for k, v in data.items() if k in allowed} if data else {}

        patient = db_driver.update_patient(patient_id, doctor_id, **updates)

        if not patient:
            return jsonify({'error': 'Patient not found'}), 404

        return jsonify({
            'message': 'Patient updated successfully',
            'patient': {
                'id': str(patient.id),
                'name': patient.get_full_name(),
                **{k: getattr(patient, k) for k in allowed if hasattr(patient, k)}
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/patients/<patient_id>", methods=["DELETE"])
@jwt_required()
def delete_patient(patient_id):
    """Delete a patient"""
    try:
        doctor_id = get_jwt_identity()

        if not db_driver.delete_patient(patient_id, doctor_id):
            return jsonify({'error': 'Patient not found'}), 404

        return jsonify({'message': 'Patient deleted successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== APPOINTMENT ROUTES ====================

@app.route("/patients/<patient_id>/sessions", methods=["POST"])
@jwt_required()
def create_session(patient_id):
    """Create a new appointment for a patient"""
    try:
        doctor_id = get_jwt_identity()
        data = request.get_json() or {}

        patient = db_driver.get_patient_by_id(patient_id, doctor_id)
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404

        appointment = db_driver.create_appointment(
            doctor_id=doctor_id,
            patient_id=patient_id,
            transcript=data.get('transcript'),
            ai_summary=data.get('ai_summary')
        )

        if not appointment:
            return jsonify({'error': 'Failed to create appointment'}), 500

        return jsonify({
            'message': 'Appointment created',
            'session': {
                'id': str(appointment.id),
                'patient_id': str(appointment.patient_id),
                'date': appointment.appointment_date.isoformat() if appointment.appointment_date else None,
                'transcript': appointment.transcript,
                'ai_summary': appointment.ai_summary
            }
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/sessions/<session_id>", methods=["PUT"])
@jwt_required()
def update_session(session_id):
    """Update appointment (transcript, ai_summary) and optionally add diagnoses/prescriptions"""
    try:
        doctor_id = get_jwt_identity()
        data = request.get_json() or {}

        updates = {}
        if 'transcript' in data:
            updates['transcript'] = data['transcript']
        if 'ai_summary' in data:
            updates['ai_summary'] = data['ai_summary']

        appointment = db_driver.update_appointment(session_id, doctor_id, **updates) if updates else db_driver.get_appointment_by_id(session_id, doctor_id)

        if not appointment:
            return jsonify({'error': 'Appointment not found'}), 404

        patient_id = appointment.patient_id
        if data.get('diagnoses'):
            for d in data['diagnoses'] if isinstance(data['diagnoses'], list) else [data['diagnoses']]:
                cond = d if isinstance(d, str) else d.get('condition_name') or d.get('diagnosis')
                if cond:
                    db_driver.add_diagnosis(appointment.id, patient_id, condition_name=cond,
                                           is_chronic=d.get('is_chronic', False) if isinstance(d, dict) else False,
                                           on_set_date=d.get('on_set_date') if isinstance(d, dict) else None)
        if data.get('prescriptions'):
            for p in data['prescriptions'] if isinstance(data['prescriptions'], list) else [data['prescriptions']]:
                name = p if isinstance(p, str) else p.get('medication_name') or p.get('medication')
                if name:
                    db_driver.add_prescription(
                        appointment.id, patient_id, medication_name=name,
                        dosage=p.get('dosage') if isinstance(p, dict) else None,
                        frequency=p.get('frequency') if isinstance(p, dict) else None,
                        start_date=p.get('start_date') if isinstance(p, dict) else None,
                        end_date=p.get('end_date') if isinstance(p, dict) else None
                    )

        appointment = db_driver.get_appointment_by_id(session_id, doctor_id)
        return jsonify({
            'message': 'Appointment updated successfully',
            'session': {
                'id': str(appointment.id),
                'transcript': appointment.transcript,
                'ai_summary': appointment.ai_summary,
                'diagnoses': [{'condition_name': d.condition_name, 'is_chronic': d.is_chronic} for d in db_driver.get_diagnoses_for_appointment(appointment.id)],
                'prescriptions': [{'medication_name': p.medication_name, 'dosage': p.dosage, 'frequency': p.frequency} for p in db_driver.get_prescriptions_for_appointment(appointment.id)]
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== PATIENT NOTES (MEMORIES) ROUTES ====================

@app.route("/patients/<patient_id>/notes", methods=["POST"])
@jwt_required()
def add_patient_note(patient_id):
    """Add a note/memory to patient record"""
    try:
        doctor_id = get_jwt_identity()
        data = request.get_json()

        if not data or 'content' not in data:
            return jsonify({'error': 'Missing note content'}), 400

        patient = db_driver.get_patient_by_id(patient_id, doctor_id)
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404

        note = db_driver.add_patient_memory(patient_id, data['content'])

        if not note:
            return jsonify({'error': 'Failed to add note'}), 500

        return jsonify({
            'message': 'Note added successfully',
            'note': {
                'id': str(note.id),
                'content': note.content,
                'date': note.created_at.isoformat() if note.created_at else None
            }
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== LIVEKIT ROOM ROUTES ====================

def generate_room_name():
    name = "room-" + str(uuid.uuid4())[:8]
    return name


@app.route("/getToken", methods=["GET"])
@jwt_required()
def get_token():
    """Get LiveKit token for video/audio consultation"""
    try:
        doctor_id = get_jwt_identity()
        doctor = db_driver.get_doctor_by_id(doctor_id)

        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        name = request.args.get("name", doctor.get_full_name() or "Doctor")
        room = request.args.get("room", None)
        patient_id = request.args.get("patient_id", "")

        if not room:
            room = generate_room_name()

        token = api.AccessToken(
            os.getenv("LIVEKIT_API_KEY"),
            os.getenv("LIVEKIT_API_SECRET")
        ).with_identity(f"doctor_{doctor_id}_{patient_id}") \
         .with_name(name) \
         .with_grants(api.VideoGrants(
            room_join=True,
            room=room,
            can_publish=True,
            can_subscribe=True
        ))

        return jsonify({
            'token': token.to_jwt(),
            'room': room,
            'url': os.getenv("LIVEKIT_URL")
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== HEALTH CHECK ====================

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({'status': 'healthy'}), 200


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        'name': 'Lia Medical Assistant API',
        'version': '1.0.0',
        'description': 'Backend API for home doctor AI assistant',
        'endpoints': {
            'auth': {
                'register': 'POST /register',
                'login': 'POST /login'
            },
            'patients': {
                'get_all': 'GET /patients',
                'get_one': 'GET /patients/<id>',
                'create': 'POST /patients',
                'update': 'PUT /patients/<id>',
                'delete': 'DELETE /patients/<id>'
            },
            'sessions': {
                'create': 'POST /patients/<id>/sessions',
                'update': 'PUT /sessions/<id>'
            },
            'notes': {
                'add': 'POST /patients/<id>/notes'
            }
        }
    }), 200


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5001, debug=True)
