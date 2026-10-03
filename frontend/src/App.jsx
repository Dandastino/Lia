import { lazy, Suspense, useState, useEffect, useCallback } from 'react';
import Login from './components/Login';
import ConnectorSettings from './components/ConnectorSettings';
import Admin from './components/Admin';

// LiveKit is heavy: load it only when a non-admin user reaches the assistant.
const VoiceInterface = lazy(() => import('./components/VoiceInterface'));
import { UNAUTHORIZED_EVENT } from './lib/api';
import { clearSession, getStoredUser, getToken, isAdminRole } from './lib/storage';

const VIEW_TITLES = {
  login: 'Sign in',
  admin: 'Administration',
  voice: 'Assistant',
  connector: 'Connector settings',
};

// Admins and owners land on the admin panel, everyone else on the assistant.
const homeViewFor = (user) => (isAdminRole(user) ? 'admin' : 'voice');

// Restore a previous session once, before the first render, so there is no
// flash of the login screen for signed-in users.
function readInitialSession() {
  const user = getToken() ? getStoredUser() : null;
  return user ? { user, view: homeViewFor(user) } : { user: null, view: 'login' };
}

function App() {
  const [initial] = useState(readInitialSession);
  const [currentView, setCurrentView] = useState(initial.view); // 'login' | 'voice' | 'connector' | 'admin'
  const [user, setUser] = useState(initial.user);

  const handleLogout = useCallback(() => {
    clearSession();
    setUser(null);
    setCurrentView('login');
  }, []);

  // The API helper emits this event when the server answers 401.
  useEffect(() => {
    window.addEventListener(UNAUTHORIZED_EVENT, handleLogout);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleLogout);
  }, [handleLogout]);

  useEffect(() => {
    document.title = `${VIEW_TITLES[currentView]} - Lia`;
  }, [currentView]);

  const handleLoginSuccess = (userData) => {
    setUser(userData);
    setCurrentView(homeViewFor(userData));
  };

  return (
    <div className="app">
      {currentView === 'login' && <Login onLoginSuccess={handleLoginSuccess} />}

      {currentView === 'admin' && user && <Admin user={user} onLogout={handleLogout} />}

      {currentView === 'voice' && user && (
        <Suspense
          fallback={
            <div className="state-box" role="status">
              <div className="spinner" aria-hidden="true" />
              <p>Loading assistant...</p>
            </div>
          }
        >
          <VoiceInterface
            user={user}
            onLogout={handleLogout}
            onOpenConnectorSettings={() => setCurrentView('connector')}
          />
        </Suspense>
      )}

      {currentView === 'connector' && user && (
        <ConnectorSettings user={user} onBack={() => setCurrentView('voice')} />
      )}
    </div>
  );
}

export default App;
