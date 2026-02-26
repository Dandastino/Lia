import { useState, useEffect } from 'react';
import axios from 'axios';
import './PatientDetail.css';

const API_URL = 'http://localhost:5001';

export default function PatientDetail({ patientId, onBack, onStartConsultation }) {
  const [patient, setPatient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showEditForm, setShowEditForm] = useState(false);
  const [editData, setEditData] = useState({});
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    fetchPatientDetails();
  }, [patientId]);

  const fetchPatientDetails = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_URL}/patients/${patientId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const { patient: p, appointments = [], notes = [] } = response.data;
      setPatient({ ...p, appointments, notes });
      setEditData(p);
    } catch (err) {
      setError('Failed to load patient details');
    } finally {
      setLoading(false);
    }
  };

  const handleEditChange = (e) => {
    const { name, value } = e.target;
    setEditData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSaveChanges = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      
      const updateData = {
        date_of_birth: editData.date_of_birth,
        gender: editData.gender,
        contact_info: editData.contact_info,
      };

      await axios.put(`${API_URL}/patients/${patientId}`, updateData, {
        headers: { Authorization: `Bearer ${token}` }
      });

      setPatient(prev => ({
        ...prev,
        ...editData
      }));
      setShowEditForm(false);
      alert('Patient information updated successfully');
    } catch (err) {
      alert('Failed to update patient: ' + (err.response?.data?.error || 'Unknown error'));
    }
  };

  if (loading) {
    return <div className="loading">Loading patient details...</div>;
  }

  if (!patient) {
    return <div className="error">Patient not found</div>;
  }

  return (
    <div className="patient-detail">
      <button className="back-btn" onClick={onBack}>← Back to Patients</button>

      <header className="detail-header">
        <div className="patient-name-section">
          <h1>{patient.name}</h1>
          <p>ID: {patient.id}</p>
        </div>
        <button 
          className="consultation-btn"
          onClick={() => onStartConsultation(patient.id)}
        >
          Start Consultation
        </button>
      </header>

      <div className="tabs">
        <button 
          className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button 
          className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => setActiveTab('history')}
        >
          History & Sessions
        </button>
        <button 
          className={`tab-btn ${activeTab === 'notes' ? 'active' : ''}`}
          onClick={() => setActiveTab('notes')}
        >
          Notes
        </button>
      </div>

      <main className="detail-content">
        {activeTab === 'overview' && (
          <section className="overview-section">
            <div className="overview-header">
              <h2>Patient Information</h2>
              <button 
                className="edit-btn"
                onClick={() => setShowEditForm(!showEditForm)}
              >
                {showEditForm ? '✕ Cancel' : '✎ Edit'}
              </button>
            </div>

            {showEditForm ? (
              <form className="edit-form" onSubmit={handleSaveChanges}>
                <div className="form-group-large">
                  <label>Date of Birth</label>
                  <input
                    type="date"
                    name="date_of_birth"
                    value={editData.date_of_birth || ''}
                    onChange={handleEditChange}
                  />
                </div>

                <div className="form-group-large">
                  <label>Gender</label>
                  <input
                    type="text"
                    name="gender"
                    value={editData.gender || ''}
                    onChange={handleEditChange}
                    placeholder="Female / Male / Other"
                  />
                </div>

                <div className="form-group-large">
                  <label>Contact Info</label>
                  <textarea
                    name="contact_info"
                    value={editData.contact_info || ''}
                    onChange={handleEditChange}
                    placeholder="Phone numbers, email, address..."
                    rows="3"
                  />
                </div>

                <button type="submit" className="save-btn">Save Changes</button>
              </form>
            ) : (
              <div className="info-grid">
                <div className="info-item">
                  <label>Patient ID</label>
                  <p>{patient.id}</p>
                </div>
                <div className="info-item">
                  <label>Date of Birth</label>
                  <p>{patient.date_of_birth ? new Date(patient.date_of_birth).toLocaleDateString() : 'Not provided'}</p>
                </div>
                <div className="info-item">
                  <label>Gender</label>
                  <p>{patient.gender || 'Not provided'}</p>
                </div>
                <div className="info-item">
                  <label>Contact Info</label>
                  <p>{patient.contact_info || 'Not provided'}</p>
                </div>
              </div>
            )}
          </section>
        )}

        {activeTab === 'history' && (
          <section className="history-section">
            <h2>Appointments</h2>
            {patient.appointments && patient.appointments.length > 0 ? (
              <div className="sessions-list">
                {patient.appointments.map((apt, idx) => (
                  <div key={idx} className="session-item">
                    <div className="session-date">{apt.date ? new Date(apt.date).toLocaleDateString() : 'Unknown date'}</div>
                    <div className="session-details">
                      <p><strong>Summary:</strong> {apt.ai_summary || apt.transcript || 'N/A'}</p>
                      {apt.diagnoses && apt.diagnoses.length > 0 && (
                        <p><strong>Diagnoses:</strong> {apt.diagnoses.map(d => d.condition_name).join(', ')}</p>
                      )}
                      {apt.prescriptions && apt.prescriptions.length > 0 && (
                        <p><strong>Prescriptions:</strong> {apt.prescriptions.map(p => p.medication_name).join(', ')}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="no-data">No previous appointments recorded</p>
            )}
          </section>
        )}

        {activeTab === 'notes' && (
          <section className="notes-section">
            <h2>Patient Notes</h2>
            {patient.notes && patient.notes.length > 0 ? (
              <div className="notes-list">
                {patient.notes.map((note, idx) => (
                  <div key={idx} className="note-item">
                    <div className="note-header">
                      <span className="note-date">{new Date(note.date).toLocaleDateString()}</span>
                    </div>
                    <p className="note-content">{note.content}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="no-data">No notes yet</p>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
