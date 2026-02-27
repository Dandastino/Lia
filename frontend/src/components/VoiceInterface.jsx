import { useState, useCallback, useEffect } from "react";
import { 
  LiveKitRoom, 
  RoomAudioRenderer, 
  useVoiceAssistant,
  VoiceAssistantControlBar,
  BarVisualizer 
} from "@livekit/components-react";
import "@livekit/components-styles";
import { api, withAuth } from "../lib/api";
import "./VoiceInterface.css";

// Voice Assistant Controls Component (must be inside LiveKitRoom)
function VoiceControls() {
  const { state, audioTrack } = useVoiceAssistant();

  const getStatusText = () => {
    switch (state) {
      case 'connecting':
        return 'Connecting...';
      case 'idle':
        return 'Ready to talk';
      case 'listening':
        return 'Listening to you...';
      case 'thinking':
        return 'Lia is thinking...';
      case 'speaking':
        return 'Lia is speaking...';
      default:
        return 'Ready';
    }
  };

  const getStatusColor = () => {
    switch (state) {
      case 'listening':
        return '#4ade80'; // green
      case 'thinking':
        return '#fbbf24'; // yellow
      case 'speaking':
        return '#60a5fa'; // blue
      default:
        return '#94a3b8'; // gray
    }
  };

  return (
    <div className="voice-controls">
      <div className="status-indicator">
        <div 
          className="status-dot" 
          style={{ backgroundColor: getStatusColor() }}
        />
        <span className="status-text">{getStatusText()}</span>
      </div>
      
      <div className="visualizer-container">
        <BarVisualizer state={state} barCount={7} trackRef={audioTrack} />
      </div>
      
      <div className="controls-buttons">
        <VoiceAssistantControlBar />
      </div>
    </div>
  );
}

const VoiceInterface = ({ user, onLogout, onOpenConnectorSettings }) => {
  const [isConnecting, setIsConnecting] = useState(true);
  const [token, setToken] = useState(null);
  const [room, setRoom] = useState(null);
  const [livekitUrl, setLivekitUrl] = useState(
    import.meta.env.VITE_LIVEKIT_URL || '',
  );
  const [error, setError] = useState('');

  const getToken = useCallback(async () => {
    try {
      setIsConnecting(true);
      setError('');
      const params = {
        name: user.email || 'User',
      };
      
      console.log('Requesting token with params:', params);
      
      const response = await api.get('/getToken', {
        params,
        ...withAuth(),
      });

      console.log('Token response:', response.data);
      setToken(response.data.token);
      setRoom(response.data.room);
      if (response.data.url) {
        setLivekitUrl(response.data.url);
      }
      setIsConnecting(false);
    } catch (err) {
      console.error('Failed to get token:', err);
      const errorMsg = err.response?.data?.error || err.response?.data?.msg || err.message || 'Failed to connect. Please try again.';
      setError(errorMsg);
      setIsConnecting(false);
    }
  }, [user]);

  // Get token on mount
  useEffect(() => {
    getToken();
  }, [getToken]);

  return (
    <div className="voice-interface">
      <div className="voice-header">
        <div className="header-left">
          <h1>🤖 Lia - Your AI Assistant</h1>
          <p className="welcome-text">Welcome, {user.email}</p>
        </div>
        <div className="header-actions">
          {user.role === 'admin' || user.role === 'owner' ? (
            <button
              className="settings-btn"
              type="button"
              onClick={onOpenConnectorSettings}
            >
              Connector Settings
            </button>
          ) : null}
          <button className="logout-btn" onClick={onLogout}>
            Logout
          </button>
        </div>
      </div>

      <div className="voice-main">
        {error && (
          <div className="error-message">
            <p>{error}</p>
            <button onClick={getToken}>Retry Connection</button>
          </div>
        )}

        {isConnecting && !error && (
          <div className="connecting">
            <div className="spinner"></div>
            <p>Connecting to Lia...</p>
          </div>
        )}

        {!isConnecting && token && room ? (
          <div className="voice-room">
            <LiveKitRoom
              serverUrl={livekitUrl}
              token={token}
              connect={true}
              video={false}
              audio={true}
            >
              <RoomAudioRenderer />
              <VoiceControls />
              
              <div className="conversation-area">
                <div className="lia-avatar">
                  <div className="avatar-circle">
                    <span>🤖</span>
                  </div>
                  <p className="avatar-label">Lia</p>
                </div>
              </div>
            </LiveKitRoom>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default VoiceInterface;
