from livekit.agents import llm
import enum
import logging
from db_driver import DatabaseDriver, Patient, Appointment
from datetime import datetime

logger = logging.getLogger("assistant")
logger.setLevel(logging.INFO)

# Create a shared DatabaseDriver instance for assistant functions
db_driver = DatabaseDriver()


class AssistantFnc:
    """AI Assistant functions for medical consultations"""

    def __init__(self, doctor_id=None):
        self.doctor_id = doctor_id
        self.current_patient: Patient = None
        self.current_appointment: Appointment = None

        self.lookup_patient_tool = llm.function_tool(
            description="Lookup a patient by name or ID to retrieve their medical history"
        )(self._lookup_patient)

        self.get_patient_context_tool = llm.function_tool(
            description="Get detailed information about the current patient including history and previous sessions"
        )(self._get_patient_context)

        self.get_patient_history_tool = llm.function_tool(
            description="Get previous medical sessions and important history for the current patient"
        )(self._get_patient_history)

        self.create_patient_tool = llm.function_tool(
            description="Create a new patient record"
        )(self._create_patient)

        self.update_patient_tool = llm.function_tool(
            description="Update patient medical information"
        )(self._update_patient)

        self.add_session_notes_tool = llm.function_tool(
            description="Add notes and findings from the current consultation session"
        )(self._add_session_notes)

        self.add_quick_note_tool = llm.function_tool(
            description="Add a quick note or observation to the patient record"
        )(self._add_quick_note)

        self.create_new_session_tool = llm.function_tool(
            description="Start a new medical session/consultation for a patient"
        )(self._create_new_session)

        self.delete_patient_tool = llm.function_tool(
            description="Delete a patient record and all associated data"
        )(self._delete_patient)

    def get_tools(self):
        return [
            self.lookup_patient_tool,
            self.get_patient_context_tool,
            self.get_patient_history_tool,
            self.create_patient_tool,
            self.update_patient_tool,
            self.add_session_notes_tool,
            self.add_quick_note_tool,
            self.create_new_session_tool,
            self.delete_patient_tool
        ]

    def set_doctor_id(self, doctor_id):
        self.doctor_id = doctor_id

    async def _lookup_patient(self, name: str | None = None, patient_id: str | None = None) -> str:
        """
        Lookup a patient by name or ID.
        - If patient_id is provided, return that specific patient (must belong to the logged-in doctor).
        - If only name is provided, return all matching patients for this doctor (supports partial matches
          on first name, last name, or full name).
        """
        logger.info("lookup patient - name: %s, id: %s", name, patient_id)

        if not self.doctor_id:
            return "Error: No doctor context"
        
        # If an explicit ID is provided, prefer that
        if patient_id is not None:
            patient = db_driver.get_patient_by_id(patient_id, self.doctor_id)
            if not patient:
                return "Patient not found for this doctor."
            self.current_patient = patient
            last_apt = db_driver.get_patient_appointments(patient.id, self.doctor_id, limit=1)
            last_visit = last_apt[0].appointment_date.strftime('%Y-%m-%d') if last_apt else 'Never'
            return (
                f"Found patient: {patient.get_full_name()} (ID: {patient.id}). "
                f"Contact: {patient.contact_info or 'Not provided'}. "
                f"Last visit: {last_visit}"
            )
        
        # Otherwise search by (partial) name among this doctor's patients
        if not name:
            patients = db_driver.get_all_patients(self.doctor_id)
            if not patients:
                return "You currently have no patients. Please create a new patient first."
            summary = "Your current patients:\n"
            for p in patients:
                summary += f"- {p.get_full_name()} (ID: {p.id})\n"
            summary += "You can ask me to select a patient by saying their name or ID."
            return summary
        
        all_patients = db_driver.get_all_patients(self.doctor_id)
        name_lower = name.lower()
        matches = [p for p in all_patients if name_lower in p.get_full_name().lower()]
        
        if not matches:
            return (
                f"No patients found with name matching '{name}' for this doctor. "
                "Would you like to create a new patient record?"
            )
        
        if len(matches) == 1:
            patient = matches[0]
            self.current_patient = patient
            last_apt = db_driver.get_patient_appointments(patient.id, self.doctor_id, limit=1)
            last_visit = last_apt[0].appointment_date.strftime('%Y-%m-%d') if last_apt else 'Never'
            return (
                f"Found patient: {patient.get_full_name()} (ID: {patient.id}). "
                f"Contact: {patient.contact_info or 'Not provided'}. "
                f"Last visit: {last_visit}"
            )
        
        # Multiple matches – list them, let the model ask user to choose
        response = f"Found {len(matches)} patients matching '{name}':\n"
        for p in matches:
            response += f"- {p.get_full_name()} (ID: {p.id})\n"
        response += (
            "Please specify which patient to use by giving me their ID or full name. "
            "Once selected, I will use that patient for this consultation."
        )
        return response

    async def _get_patient_context(self) -> str:
        """Get comprehensive context about the current patient."""
        logger.info("get patient context - patient: %s",
                    self.current_patient.id if self.current_patient else None)

        if not self.current_patient:
            return "No patient selected. Please lookup a patient first."

        patient = self.current_patient
        age = self._calculate_age(patient.date_of_birth)
        context = f"""
PATIENT: {patient.get_full_name()}
Age: {age} years old
Gender: {patient.gender or 'Not specified'}
Contact: {patient.contact_info or 'Not provided'}
"""
        diagnoses = db_driver.get_diagnoses_for_patient(patient.id, limit=20)
        if diagnoses:
            context += "\nDIAGNOSES: " + "; ".join(d.condition_name + (" (chronic)" if d.is_chronic else "") for d in diagnoses)
        prescriptions = db_driver.get_prescriptions_for_patient(patient.id, limit=20)
        if prescriptions:
            context += "\nPRESCRIPTIONS: " + "; ".join(
                f"{p.medication_name}" + (f" {p.dosage or ''} {p.frequency or ''}" if (p.dosage or p.frequency) else "") for p in prescriptions
            )
        memories = db_driver.get_patient_memories(patient.id, limit=10)
        if memories:
            context += "\nNOTES/MEMORIES: " + " | ".join(m.content[:80] + ("..." if len(m.content) > 80 else "") for m in memories)
        return context

    async def _get_patient_history(self, num_sessions: int = 3) -> str:
        """Get previous appointments and history for the patient."""
        logger.info("get patient history - patient: %s",
                    self.current_patient.id if self.current_patient else None)

        if not self.current_patient:
            return "No patient selected."

        appointments = db_driver.get_patient_appointments(
            self.current_patient.id,
            self.doctor_id,
            limit=num_sessions
        )

        if not appointments:
            return f"No previous appointments recorded for {self.current_patient.get_full_name()}"

        history = f"PREVIOUS APPOINTMENTS FOR {self.current_patient.get_full_name()}:\n\n"
        for i, apt in enumerate(appointments, 1):
            history += f"APPOINTMENT {i} - {apt.appointment_date.strftime('%Y-%m-%d %H:%M')}\n"
            history += f"  Summary: {apt.ai_summary or 'N/A'}\n"
            diag = db_driver.get_diagnoses_for_appointment(apt.id)
            if diag:
                history += f"  Diagnoses: {', '.join(d.condition_name for d in diag)}\n"
            rx = db_driver.get_prescriptions_for_appointment(apt.id)
            if rx:
                history += f"  Prescriptions: {', '.join(p.medication_name for p in rx)}\n"
            history += "\n"
        return history

    async def _create_patient(self, first_name: str, last_name: str, date_of_birth: str,
                              gender: str = None, contact_info: str = None) -> str:
        """Create a new patient record. date_of_birth format: YYYY-MM-DD."""
        logger.info("create patient - name: %s %s", first_name, last_name)

        if not self.doctor_id:
            return "Error: No doctor context"

        patient = db_driver.create_patient(
            self.doctor_id,
            first_name,
            last_name,
            date_of_birth=date_of_birth,
            gender=gender,
            contact_info=contact_info
        )

        if not patient:
            return "Failed to create patient"

        self.current_patient = patient
        return f"Patient {patient.get_full_name()} created successfully (ID: {patient.id})"

    async def _update_patient(self, first_name: str = None, last_name: str = None,
                              date_of_birth: str = None, gender: str = None,
                              contact_info: str = None) -> str:
        """Update patient information."""
        logger.info("update patient - patient: %s",
                    self.current_patient.id if self.current_patient else None)

        if not self.current_patient:
            return "No patient selected"

        updates = {}
        if first_name is not None:
            updates['first_name'] = first_name
        if last_name is not None:
            updates['last_name'] = last_name
        if date_of_birth is not None:
            updates['date_of_birth'] = date_of_birth
        if gender is not None:
            updates['gender'] = gender
        if contact_info is not None:
            updates['contact_info'] = contact_info

        updated = db_driver.update_patient(
            self.current_patient.id,
            self.doctor_id,
            **updates
        )

        if not updated:
            return "Failed to update patient"

        self.current_patient = updated
        return "Patient information updated successfully"

    async def _delete_patient(self, patient_id: str | None = None, first_name: str | None = None,
                              last_name: str | None = None) -> str:
        """Delete a patient record."""
        logger.info("delete patient - id: %s, name: %s %s", patient_id, first_name, last_name)

        if not self.doctor_id:
            return "Error: No doctor context"

        patient_to_delete = None
        if patient_id is not None:
            patient_to_delete = db_driver.get_patient_by_id(patient_id, self.doctor_id)
        elif first_name and last_name:
            all_patients = db_driver.get_all_patients(self.doctor_id)
            name_search = f"{first_name} {last_name}".lower()
            for p in all_patients:
                if p.get_full_name().lower() == name_search:
                    patient_to_delete = p
                    break

        if not patient_to_delete:
            return "Patient not found. Cannot delete."

        patient_name = patient_to_delete.get_full_name()
        success = db_driver.delete_patient(patient_to_delete.id, self.doctor_id)

        if not success:
            return f"Failed to delete patient {patient_name}"

        if self.current_patient and str(self.current_patient.id) == str(patient_to_delete.id):
            self.current_patient = None
            self.current_appointment = None

        return f"Patient {patient_name} has been successfully deleted from the system"

    async def _create_new_session(self, transcript: str = None, ai_summary: str = None) -> str:
        """Start a new appointment/consultation for the current patient."""
        logger.info("create session - patient: %s",
                    self.current_patient.id if self.current_patient else None)

        if not self.current_patient:
            return "No patient selected"

        apt = db_driver.create_appointment(
            self.doctor_id,
            self.current_patient.id,
            transcript=transcript,
            ai_summary=ai_summary
        )

        if not apt:
            return "Failed to create appointment"

        self.current_appointment = apt
        return f"New consultation started for {self.current_patient.get_full_name()}"

    async def _add_session_notes(self, examination_findings: str = None, diagnosis: str = None,
                                 treatment_plan: str = None, medications_prescribed: str = None,
                                 follow_up_notes: str = None, ai_summary: str = None,
                                 transcript: str = None) -> str:
        """Add findings to current appointment: update summary and optionally add diagnosis/prescription records."""
        logger.info("add session notes - appointment: %s",
                    self.current_appointment.id if self.current_appointment else None)

        if not self.current_appointment:
            return "No active appointment. Create a new session first."

        # Build ai_summary from parts if not provided
        summary_parts = []
        if ai_summary:
            summary_parts.append(ai_summary)
        if examination_findings:
            summary_parts.append(f"Findings: {examination_findings}")
        if treatment_plan:
            summary_parts.append(f"Treatment: {treatment_plan}")
        if follow_up_notes:
            summary_parts.append(f"Follow-up: {follow_up_notes}")
        combined_summary = "\n".join(summary_parts) if summary_parts else None

        updates = {}
        if combined_summary is not None:
            updates['ai_summary'] = combined_summary
        if transcript is not None:
            updates['transcript'] = transcript

        if updates:
            db_driver.update_appointment(
                self.current_appointment.id,
                self.doctor_id,
                **updates
            )

        patient_id = self.current_patient.id
        apt_id = self.current_appointment.id

        if diagnosis:
            for cond in (c.strip() for c in diagnosis.replace(",", ";").split(";") if c.strip()):
                db_driver.add_diagnosis(apt_id, patient_id, condition_name=cond)

        if medications_prescribed:
            for med in (m.strip() for m in medications_prescribed.replace(",", ";").split(";") if m.strip()):
                db_driver.add_prescription(apt_id, patient_id, medication_name=med)

        return "Session notes saved successfully"

    async def _add_quick_note(self, note_content: str, note_type: str = "update") -> str:
        """Add a quick note/memory to the patient record."""
        logger.info("add quick note - patient: %s",
                    self.current_patient.id if self.current_patient else None)

        if not self.current_patient:
            return "No patient selected"

        content = f"[{note_type}] {note_content}" if note_type and note_type != "update" else note_content
        note = db_driver.add_patient_memory(self.current_patient.id, content)

        if not note:
            return "Failed to add note"

        return f"Note added to {self.current_patient.get_full_name()}'s record"

    @staticmethod
    def _calculate_age(date_of_birth) -> int:
        if not date_of_birth:
            return None
        from datetime import date
        today = date.today()
        age = today.year - date_of_birth.year - \
              ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
        return age
