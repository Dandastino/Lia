from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from typing import Optional, List
from uuid import UUID
import bcrypt
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

db = SQLAlchemy()


def _uuid_server_default():
    return db.text("uuid_generate_v4()")


class Doctor(db.Model):
    """Doctor/healthcare provider model"""
    __tablename__ = 'doctors'

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    specialty = db.Column(db.String(100))
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    patients = db.relationship('Patient', backref='primary_doctor', lazy=True, foreign_keys='Patient.primary_doctor_id')
    appointments = db.relationship('Appointment', backref='doctor', lazy=True)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))


class Patient(db.Model):
    """Patient model"""
    __tablename__ = 'patients'

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    primary_doctor_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey('doctors.id', ondelete='SET NULL'))
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(20))
    contact_info = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    appointments = db.relationship('Appointment', backref='patient', lazy=True, cascade='all, delete-orphan')
    diagnoses = db.relationship('Diagnosis', backref='patient', lazy=True, cascade='all, delete-orphan')
    prescriptions = db.relationship('Prescription', backref='patient', lazy=True, cascade='all, delete-orphan')
    memories = db.relationship('PatientMemory', backref='patient', lazy=True, cascade='all, delete-orphan')

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"


class Appointment(db.Model):
    """Appointment / consultation session"""
    __tablename__ = 'appointments'

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    patient_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False)
    doctor_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey('doctors.id'))
    appointment_date = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    transcript = db.Column(db.Text)
    ai_summary = db.Column(db.Text)

    diagnoses = db.relationship('Diagnosis', backref='appointment', lazy=True, cascade='all, delete-orphan')
    prescriptions = db.relationship('Prescription', backref='appointment', lazy=True, cascade='all, delete-orphan')


class Diagnosis(db.Model):
    """Diagnosis linked to an appointment and patient"""
    __tablename__ = 'diagnoses'

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    appointment_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey('appointments.id', ondelete='CASCADE'))
    patient_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False)
    condition_name = db.Column(db.String(255), nullable=False)
    is_chronic = db.Column(db.Boolean, default=False)
    on_set_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())


class Prescription(db.Model):
    """Prescription linked to an appointment and patient"""
    __tablename__ = 'prescriptions'

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    appointment_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey('appointments.id', ondelete='CASCADE'))
    patient_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False)
    medication_name = db.Column(db.String(255), nullable=False)
    dosage = db.Column(db.String(100))
    frequency = db.Column(db.String(100))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())


class PatientMemory(db.Model):
    """Knowledge/memory about a patient"""
    __tablename__ = 'patient_memories'

    id = db.Column(PG_UUID(as_uuid=True), primary_key=True, server_default=_uuid_server_default())
    patient_id = db.Column(PG_UUID(as_uuid=True), db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())


class DatabaseDriver:
    """Database driver for medical records"""

    def __init__(self, app=None):
        self.app = app

    def init_app(self, app):
        self.app = app
        db.init_app(app)
        with app.app_context():
            db.create_all()

    def _doctor_id(self, doctor_id):
        """
        Safely normalize a doctor_id to a UUID.
        Returns None if the value cannot be parsed, instead of raising.
        """
        if not doctor_id:
            return None
        if isinstance(doctor_id, UUID):
            return doctor_id
        try:
            return UUID(str(doctor_id))
        except (ValueError, TypeError):
            return None

    def _patient_id(self, patient_id):
        if patient_id is None:
            return None
        return patient_id if isinstance(patient_id, UUID) else UUID(str(patient_id))

    def _uuid_any(self, value):
        if value is None:
            return None
        return value if isinstance(value, UUID) else UUID(str(value))

    # Doctor methods
    def create_doctor(self, email: str, password: str, first_name: str, last_name: str,
                      specialty: str = None) -> Optional[Doctor]:
        if Doctor.query.filter_by(email=email).first():
            return None
        doctor = Doctor(
            email=email,
            first_name=first_name,
            last_name=last_name,
            specialty=specialty
        )
        doctor.set_password(password)
        db.session.add(doctor)
        db.session.commit()
        return doctor

    def get_doctor_by_email(self, email: str) -> Optional[Doctor]:
        return Doctor.query.filter_by(email=email).first()

    def get_doctor_by_id(self, doctor_id) -> Optional[Doctor]:
        return Doctor.query.get(self._doctor_id(doctor_id))

    # Patient methods
    def create_patient(self, primary_doctor_id, first_name: str, last_name: str, date_of_birth,
                       gender: str = None, contact_info: str = None) -> Optional[Patient]:
        doc_id = self._doctor_id(primary_doctor_id)
        if isinstance(date_of_birth, str):
            date_of_birth = datetime.strptime(date_of_birth, '%Y-%m-%d').date() if date_of_birth else None
        patient = Patient(
            primary_doctor_id=doc_id,
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            gender=gender,
            contact_info=contact_info
        )
        db.session.add(patient)
        db.session.commit()
        return patient

    def get_patient_by_id(self, patient_id, doctor_id=None) -> Optional[Patient]:
        pid = self._patient_id(patient_id)
        q = Patient.query.filter_by(id=pid)
        if doctor_id is not None:
            doc_id = self._doctor_id(doctor_id)
            if doc_id is not None:
                q = q.filter_by(primary_doctor_id=doc_id)
        return q.first()

    def get_all_patients(self, doctor_id) -> List[Patient]:
        """
        Get all patients for a specific doctor.
        If the doctor_id is invalid, return an empty list.
        """
        doc_id = self._doctor_id(doctor_id)
        if doc_id is None:
            return []
        return Patient.query.filter_by(primary_doctor_id=doc_id).all()

    def update_patient(self, patient_id, doctor_id, **kwargs) -> Optional[Patient]:
        patient = self.get_patient_by_id(patient_id, doctor_id)
        if not patient:
            return None
        allowed = {'first_name', 'last_name', 'date_of_birth', 'gender', 'contact_info', 'primary_doctor_id'}
        for key, value in kwargs.items():
            if key in allowed and value is not None:
                if key == 'date_of_birth' and isinstance(value, str):
                    value = datetime.strptime(value, '%Y-%m-%d').date()
                setattr(patient, key, value)
        db.session.commit()
        return patient

    def delete_patient(self, patient_id, doctor_id) -> bool:
        patient = self.get_patient_by_id(patient_id, doctor_id)
        if not patient:
            return False
        db.session.delete(patient)
        db.session.commit()
        return True

    # Appointment methods
    def create_appointment(self, doctor_id, patient_id, transcript: str = None,
                           ai_summary: str = None) -> Optional[Appointment]:
        doc_id = self._doctor_id(doctor_id)
        pid = self._patient_id(patient_id)
        apt = Appointment(patient_id=pid, doctor_id=doc_id, transcript=transcript, ai_summary=ai_summary)
        db.session.add(apt)
        db.session.commit()
        return apt

    def update_appointment(self, appointment_id, doctor_id, **kwargs) -> Optional[Appointment]:
        aid = self._uuid_any(appointment_id)
        apt = Appointment.query.filter_by(id=aid, doctor_id=self._doctor_id(doctor_id)).first()
        if not apt:
            return None
        for key in ('transcript', 'ai_summary'):
            if key in kwargs and kwargs[key] is not None:
                setattr(apt, key, kwargs[key])
        db.session.commit()
        return apt

    def get_appointment_by_id(self, appointment_id, doctor_id) -> Optional[Appointment]:
        aid = self._uuid_any(appointment_id)
        return Appointment.query.filter_by(id=aid, doctor_id=self._doctor_id(doctor_id)).first()

    def get_patient_appointments(self, patient_id, doctor_id, limit: int = 5) -> List[Appointment]:
        pid = self._patient_id(patient_id)
        doc_id = self._doctor_id(doctor_id)
        return Appointment.query.filter_by(patient_id=pid, doctor_id=doc_id)\
            .order_by(Appointment.appointment_date.desc()).limit(limit).all()

    # Diagnosis methods
    def add_diagnosis(self, appointment_id, patient_id, condition_name: str,
                      is_chronic: bool = False, on_set_date=None) -> Optional[Diagnosis]:
        aid = self._uuid_any(appointment_id)
        pid = self._patient_id(patient_id)
        if isinstance(on_set_date, str) and on_set_date:
            on_set_date = datetime.strptime(on_set_date, '%Y-%m-%d').date()
        d = Diagnosis(
            appointment_id=aid,
            patient_id=pid,
            condition_name=condition_name,
            is_chronic=is_chronic,
            on_set_date=on_set_date
        )
        db.session.add(d)
        db.session.commit()
        return d

    def get_diagnoses_for_patient(self, patient_id, limit: int = 50) -> List[Diagnosis]:
        pid = self._patient_id(patient_id)
        return Diagnosis.query.filter_by(patient_id=pid)\
            .order_by(Diagnosis.created_at.desc()).limit(limit).all()

    def get_diagnoses_for_appointment(self, appointment_id) -> List[Diagnosis]:
        aid = self._uuid_any(appointment_id)
        return Diagnosis.query.filter_by(appointment_id=aid).all()

    # Prescription methods
    def add_prescription(self, appointment_id, patient_id, medication_name: str,
                         dosage: str = None, frequency: str = None,
                         start_date=None, end_date=None) -> Optional[Prescription]:
        aid = self._uuid_any(appointment_id)
        pid = self._patient_id(patient_id)
        if isinstance(start_date, str) and start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str) and end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        p = Prescription(
            appointment_id=aid,
            patient_id=pid,
            medication_name=medication_name,
            dosage=dosage,
            frequency=frequency,
            start_date=start_date,
            end_date=end_date
        )
        db.session.add(p)
        db.session.commit()
        return p

    def get_prescriptions_for_patient(self, patient_id, limit: int = 50) -> List[Prescription]:
        pid = self._patient_id(patient_id)
        return Prescription.query.filter_by(patient_id=pid)\
            .order_by(Prescription.created_at.desc()).limit(limit).all()

    def get_prescriptions_for_appointment(self, appointment_id) -> List[Prescription]:
        aid = self._uuid_any(appointment_id)
        return Prescription.query.filter_by(appointment_id=aid).all()

    # Patient memories (notes)
    def add_patient_memory(self, patient_id, content: str) -> Optional[PatientMemory]:
        pid = self._patient_id(patient_id)
        m = PatientMemory(patient_id=pid, content=content)
        db.session.add(m)
        db.session.commit()
        return m

    def get_patient_memories(self, patient_id, limit: int = 10) -> List[PatientMemory]:
        pid = self._patient_id(patient_id)
        return PatientMemory.query.filter_by(patient_id=pid)\
            .order_by(PatientMemory.created_at.desc()).limit(limit).all()
