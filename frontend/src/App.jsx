import { useState, useEffect } from 'react';
import './App.css';
import Login from './components/Login';
import VoiceInterface from './components/VoiceInterface';
import ConnectorSettings from './components/ConnectorSettings';
import Admin from './components/Admin';

function App() {
  const [currentView, setCurrentView] = useState('login'); // 'login' | 'voice' | 'connector' | 'admin'
  const [user, setUser] = useState(null);

  useEffect(() => {
    // Check if user is already logged in
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');

    if (token && userData) {
      const parsedUser = JSON.parse(userData);
      setUser(parsedUser);
      // Route admin users to admin dashboard, others to voice interface
      setCurrentView(parsedUser.role === 'admin' ? 'admin' : 'voice');
    }
  }, []);

  const handleLoginSuccess = (userData) => {
    setUser(userData);
    // Route admin users to admin dashboard, others to voice interface
    setCurrentView(userData.role === 'admin' ? 'admin' : 'voice');
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setUser(null);
    setCurrentView('login');
  };

  const handleOpenConnectorSettings = () => {
    setCurrentView('connector');
  };

  const handleBackToVoice = () => {
    setCurrentView('voice');
  };

  return (
    <div className="app">
      {currentView === 'login' && (
        <Login onLoginSuccess={handleLoginSuccess} />
      )}

      {currentView === 'admin' && user && (
        <Admin user={user} onLogout={handleLogout} />
      )}

      {currentView === 'voice' && user && (
        <VoiceInterface
          user={user}
          onLogout={handleLogout}
          onOpenConnectorSettings={handleOpenConnectorSettings}
        />
      )}

      {currentView === 'connector' && user && (
        <ConnectorSettings user={user} onBack={handleBackToVoice} />
      )}
    </div>
  );
}

export default App;


