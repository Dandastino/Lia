import React, { useState, useCallback, useEffect, useRef } from "react";
import { 
  LiveKitRoom, 
  RoomAudioRenderer, 
  useVoiceAssistant,
  useRoomContext,
  useDataChannel,
  useLocalParticipant
} from "@livekit/components-react";
import "@livekit/components-styles";
import { api } from "../lib/api";
import { RoomEvent } from "livekit-client";
import "./VoiceInterface.css";

// Voice Assistant Controls Component (must be inside LiveKitRoom)
function VoiceControls({ onDisconnect }) {
  const { state, audioTrack } = useVoiceAssistant();
  const room = useRoomContext();
  const { isMicrophoneEnabled, microphoneTrack } = useLocalParticipant();
  const [messages, setMessages] = useState([]);
  const [currentUserTranscript, setCurrentUserTranscript] = useState('');
  const [currentAgentTranscript, setCurrentAgentTranscript] = useState('');
  const [showDevices, setShowDevices] = useState(false);
  const [microphones, setMicrophones] = useState([]);
  const [activeMicId, setActiveMicId] = useState('');
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentUserTranscript, currentAgentTranscript]);

  useEffect(() => {
    const loadMicrophones = async () => {
      try {
        const allDevices = await navigator.mediaDevices.enumerateDevices();
        const inputs = allDevices.filter((device) => device.kind === 'audioinput');
        setMicrophones(inputs);

        if (!activeMicId && inputs.length > 0) {
          setActiveMicId(inputs[0].deviceId);
        }
      } catch (error) {
        console.error('Error loading microphones:', error);
      }
    };

    loadMicrophones();
    navigator.mediaDevices.addEventListener('devicechange', loadMicrophones);

    return () => {
      navigator.mediaDevices.removeEventListener('devicechange', loadMicrophones);
    };
  }, [activeMicId]);

  // Monitor user's audio level to detect when they're speaking
  useEffect(() => {
    if (!microphoneTrack || !isMicrophoneEnabled) {
      setIsUserSpeaking(false);
      return;
    }

    let animationFrameId;
    let audioContext;
    let analyser;
    let dataArray;

    const setupAudioAnalysis = async () => {
      try {
        const streamTrack = microphoneTrack?.track?.mediaStreamTrack;
        if (!streamTrack) return;
        const mediaStream = new MediaStream([streamTrack]);
        if (!mediaStream) return;

        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        const source = audioContext.createMediaStreamSource(mediaStream);
        source.connect(analyser);
        analyser.fftSize = 256;
        
        const bufferLength = analyser.frequencyBinCount;
        dataArray = new Uint8Array(bufferLength);

        const checkAudioLevel = () => {
          analyser.getByteFrequencyData(dataArray);
          const average = dataArray.reduce((a, b) => a + b) / bufferLength;
          
          // Threshold for detecting speech (adjust as needed)
          setIsUserSpeaking(average > 15);
          
          animationFrameId = requestAnimationFrame(checkAudioLevel);
        };

        checkAudioLevel();
      } catch (error) {
        console.error('Error setting up audio analysis:', error);
      }
    };

    setupAudioAnalysis();

    return () => {
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
      if (audioContext) {
        audioContext.close();
      }
    };
  }, [microphoneTrack, isMicrophoneEnabled]);

  // Listen for transcription events from LiveKit
  useEffect(() => {
    if (!room) return;

    const handleTranscriptionReceived = (transcriptions) => {
      transcriptions.forEach((transcription) => {
        const { segments, participant } = transcription;
        
        segments.forEach((segment) => {
          const text = segment.text;
          const isFinal = segment.final;
          const isAgent = participant?.identity?.includes('agent') || participant?.identity?.includes('assistant');

          if (isFinal && text.trim()) {
            // Add completed message to history
            setMessages(prev => [...prev, {
              type: isAgent ? 'ai' : 'user',
              text: text.trim()
            }]);
            
            // Clear the temporary transcript
            if (isAgent) {
              setCurrentAgentTranscript('');
            } else {
              setCurrentUserTranscript('');
            }
          } else if (!isFinal && text.trim()) {
            // Update temporary transcript (typing effect)
            if (isAgent) {
              setCurrentAgentTranscript(text.trim());
            } else {
              setCurrentUserTranscript(text.trim());
            }
          }
        });
      });
    };

    // Subscribe to transcription events
    room.on(RoomEvent.TranscriptionReceived, handleTranscriptionReceived);

    return () => {
      room.off(RoomEvent.TranscriptionReceived, handleTranscriptionReceived);
    };
  }, [room]);

  // Alternative: Listen for agent messages via data channel
  useDataChannel((message) => {
    try {
      const data = JSON.parse(message.payload);
      
      // Handle different message types from the agent
      if (data.type === 'transcript' && data.text) {
        setMessages(prev => [...prev, {
          type: data.role === 'assistant' ? 'ai' : 'user',
          text: data.text
        }]);
      }
    } catch (error) {
      console.error('Error parsing data channel message:', error);
    }
  });

  const getStatusIndicator = () => {
    switch (state) {
      case 'connecting':
        return (
          <div className="status-indicator connecting">
            <div className="typing-dots">
              <span></span><span></span><span></span>
            </div>
            <span>Connecting...</span>
          </div>
        );
      case 'listening':
        return (
          <div className="status-indicator listening">
            <div className="pulse-dot"></div>
            <span>{isUserSpeaking ? 'You are speaking...' : 'Listening...'}</span>
          </div>
        );
      case 'thinking':
        return (
          <div className="status-indicator thinking">
            <div className="typing-dots">
              <span></span><span></span><span></span>
            </div>
            <span>Lia is thinking...</span>
          </div>
        );
      case 'speaking':
        return (
          <div className="status-indicator speaking">
            <div className="pulse-dot speaking"></div>
            <span>Lia is speaking...</span>
          </div>
        );
      default:
        return (
          <div className="status-indicator idle">
            <div className="ready-dot"></div>
            <span>Ready to talk</span>
          </div>
        );
    }
  };

  return (
    <div className="conversation-box">
      <div className="conversation-header">
        <h2>Conversation with Lia</h2>
        {getStatusIndicator()}
      </div>
      
      <div className="messages-container">
        {messages.length === 0 && !currentUserTranscript && !currentAgentTranscript && (
          <div className="welcome-message">
            <div className="sound-wave-container">
              <div className={`sound-wave ${state === 'speaking' || isUserSpeaking ? 'active' : ''} ${isUserSpeaking ? 'user-speaking' : ''}`}>
                <span className="wave-bar"></span>
                <span className="wave-bar"></span>
                <span className="wave-bar"></span>
                <span className="wave-bar"></span>
                <span className="wave-bar"></span>
                <span className="wave-bar"></span>
                <span className="wave-bar"></span>
              </div>
            </div>
            {(state === 'speaking' || isUserSpeaking) && (
              <p className="wave-label">
                {isUserSpeaking ? '🎤 You are speaking' : '🤖 Lia is speaking'}
              </p>
            )}
          </div>
        )}
        
        {messages.map((msg, index) => (
          <div key={index} className={`message ${msg.type}`}>
            <div className="message-avatar">
              {msg.type === 'user' ? '👤' : '🤖'}
            </div>
            <div className="message-content">
              <div className="message-text">{msg.text}</div>
            </div>
          </div>
        ))}
        
        {currentUserTranscript && (
          <div className="message user typing">
            <div className="message-avatar">👤</div>
            <div className="message-content">
              <div className="message-text">{currentUserTranscript}<span className="cursor">|</span></div>
            </div>
          </div>
        )}
        
        {currentAgentTranscript && (
          <div className="message ai typing">
            <div className="message-avatar">🤖</div>
            <div className="message-content">
              <div className="message-text">{currentAgentTranscript}<span className="cursor">|</span></div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      <div className="controls-buttons">
        {/* Mute/Unmute Microphone */}
        <button
          className="control-btn mic-btn"
          onClick={async () => {
            if (room?.localParticipant) {
              await room.localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled);
            }
          }}
          title={isMicrophoneEnabled ? "Mute Microphone" : "Unmute Microphone"}
          data-active={isMicrophoneEnabled}
        >
          {isMicrophoneEnabled ? (
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
              <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28zm-4.02.17c0-.06.02-.11.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c.57-.08 1.12-.24 1.64-.46l5.09 5.09L21 21.27 4.27 3z"/>
            </svg>
          )}
        </button>

        {/* Device Selector */}
        <div className="device-selector-wrapper">
          <button
            className="control-btn device-btn"
            onClick={() => setShowDevices(!showDevices)}
            title="Select Microphone"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 1c-4.97 0-9 4.03-9 9v7c0 1.66 1.34 3 3 3h3v-8H5v-2c0-3.87 3.13-7 7-7s7 3.13 7 7v2h-4v8h3c1.66 0 3-1.34 3-3v-7c0-4.97-4.03-9-9-9z"/>
            </svg>
          </button>
          {showDevices && microphones.length > 0 && (
            <div className="device-dropdown">
              {microphones.map((device, index) => (
                <button
                  key={device.deviceId}
                  className={`device-option ${activeMicId === device.deviceId ? 'active' : ''}`}
                  onClick={async () => {
                    if (room && device.deviceId && device.deviceId !== activeMicId) {
                      await room.switchActiveDevice('audioinput', device.deviceId);
                      setActiveMicId(device.deviceId);
                    }
                    setShowDevices(false);
                  }}
                >
                  {device.label || `Microphone ${index + 1}`}
                  {activeMicId === device.deviceId && (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                    </svg>
                  )}
                </button>
              ))}
            </div>
          )}
          {showDevices && microphones.length === 0 && (
            <div className="device-dropdown">
              <button className="device-option" type="button" disabled>
                No microphones found
              </button>
            </div>
          )}
        </div>

        {/* Disconnect Button */}
        <button
          className="control-btn disconnect-btn"
          onClick={onDisconnect}
          title="Disconnect"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
          </svg>
        </button>
      </div>
    </div>
  );
}


const VoiceInterface = ({ user, onLogout, onOpenConnectorSettings }) => {
  const [isConnecting, setIsConnecting] = useState(true);
  const [isConnected, setIsConnected] = useState(false);
  const [token, setToken] = useState(null);
  const [room, setRoom] = useState(null);
  const [livekitUrl, setLivekitUrl] = useState(
    import.meta.env.VITE_LIVEKIT_URL || '',
  );
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('conversation');

  const isValidWebSocketUrl = (value) => {
    if (!value || typeof value !== 'string') return false;
    return value.startsWith('ws://') || value.startsWith('wss://');
  };

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
      });

      console.log('Token response:', response.data);

      const nextToken = response?.data?.token;
      const nextRoom = response?.data?.room;
      const nextUrl = response?.data?.url || import.meta.env.VITE_LIVEKIT_URL || '';

      if (!nextToken || !nextRoom) {
        setError('LiveKit token generation failed. Please check backend LiveKit API key/secret.');
        setIsConnecting(false);
        return;
      }

      if (!isValidWebSocketUrl(nextUrl)) {
        setError('LiveKit URL is missing or invalid. Set LIVEKIT_URL in backend environment (ws:// or wss://).');
        setIsConnecting(false);
        return;
      }

      setToken(nextToken);
      setRoom(nextRoom);
      setLivekitUrl(nextUrl);
      setIsConnecting(false);
      setIsConnected(true);
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

  const handleDisconnect = () => {
    setIsConnected(false);
    setToken(null);
    setRoom(null);
  };

  const handleConnect = () => {
    getToken();
  };

  return (
    <div className="voice-container">
      {/* Header - Same style as Admin */}
      <div className="voice-header">
        <h1>Lia - Your Personal AI Assistant</h1>
        <div className="voice-header-user-info">
          <span>Logged in as: <strong>{user.name || user.email}</strong></span>
          {user.role === 'admin' || user.role === 'owner' ? (
            <button
              className="voice-header-btn"
              type="button"
              onClick={onOpenConnectorSettings}
              title="Settings"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3"/>
                <path d="M12 1v6m0 6v6m5.2-13.2l-4.2 4.2m0 6l4.2 4.2M23 12h-6m-6 0H1m13.2 5.2l-4.2-4.2m0-6l-4.2-4.2"/>
              </svg>
              <span>Settings</span>
            </button>
          ) : null}
          {error && (
            <button className="voice-header-btn reconnect-btn" onClick={getToken} title="Reconnect">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
                <path d="M21 3v5h-5"/>
                <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
                <path d="M3 21v-5h5"/>
              </svg>
              <span>Reconnect</span>
            </button>
          )}
          <button className="voice-header-btn logout-btn" onClick={onLogout} title="Logout">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            <span>Logout</span>
          </button>
        </div>
      </div>

      {/* Main Content Area - Same style as Admin */}
      <div className="voice-content">
        {error && <div className="alert alert-error">{error}</div>}

        {/* Conversation Tab */}
        {activeTab === 'conversation' && (
          <div className="tab-content">
            {isConnecting && !error && (
              <div className="connecting">
                <div className="spinner"></div>
                <p>Connecting to Lia...</p>
              </div>
            )}

            {!isConnected && !isConnecting && (
              <div className="disconnected-state">
                <div className="disconnected-icon">
                  <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                </div>
                <h3>Disconnected from Lia</h3>
                <p>Click the button below to reconnect</p>
                <button className="connect-btn" onClick={handleConnect}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                  </svg>
                  Connect
                </button>
              </div>
            )}

            {isConnected && token && room && isValidWebSocketUrl(livekitUrl) ? (
              <LiveKitRoom
                serverUrl={livekitUrl}
                token={token}
                connect={true}
                video={false}
                audio={true}
              >
                <RoomAudioRenderer />
                <VoiceControls onDisconnect={handleDisconnect} />
              </LiveKitRoom>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
};

export default VoiceInterface;
