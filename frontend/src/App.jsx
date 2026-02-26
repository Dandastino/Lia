import { useState, useEffect } from 'react'
import './App.css'
import Login from './components/Login'
import VoiceInterface from './components/VoiceInterface'

function App() {
  const [currentView, setCurrentView] = useState('login');
  const [doctor, setDoctor] = useState(null);

  useEffect(() => {
    // Check if user is already logged in
    const token = localStorage.getItem('token');
    const doctorData = localStorage.getItem('doctor');
    
    if (token && doctorData) {
      setDoctor(JSON.parse(doctorData));
      setCurrentView('voice');
    }
  }, []);

  const handleLoginSuccess = (doctorData) => {
    setDoctor(doctorData);
    setCurrentView('voice');
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('doctor');
    setDoctor(null);
    setCurrentView('login');
  };

  return (
    <div className="app">
      {currentView === 'login' && (
        <Login onLoginSuccess={handleLoginSuccess} />
      )}

      {currentView === 'voice' && doctor && (
        <VoiceInterface 
          doctor={doctor}
          onLogout={handleLogout}
        />
      )}
    </div>
  )
}

export default App

