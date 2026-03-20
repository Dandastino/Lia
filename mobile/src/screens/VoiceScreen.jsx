import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
  Platform,
  PermissionsAndroid,
  Animated,
  Easing,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  LiveKitRoom,
  AudioSession,
  registerGlobals,
  useLocalParticipant,
  useRemoteParticipants,
  useRoomContext,
} from '@livekit/react-native';
import { RoomEvent } from 'livekit-client';
import { api } from '../lib/api';
import { storage } from '../lib/storage';
import { styles, waveStyles, statusStyles } from './VoiceScreen.styles';

let liveKitGlobalsRegistered = false;

function ensureLiveKitGlobals() {
  if (liveKitGlobalsRegistered) {
    return;
  }

  registerGlobals();
  liveKitGlobalsRegistered = true;
}

// ─── Waveform bars (animated when active) ──────────────────────────────────

function WaveformDisplay({ active, isUser }) {
  const bars = useRef([...Array(7)].map(() => new Animated.Value(0.3))).current;

  useEffect(() => {
    if (!active) {
      bars.forEach((bar) => Animated.timing(bar, { toValue: 0.3, duration: 200, useNativeDriver: true }).start());
      return;
    }
    const animations = bars.map((bar, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(bar, {
            toValue: 0.3 + Math.random() * 0.7,
            duration: 300 + i * 60,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
          Animated.timing(bar, {
            toValue: 0.2 + Math.random() * 0.4,
            duration: 300 + i * 60,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
        ])
      )
    );
    animations.forEach((a) => a.start());
    return () => animations.forEach((a) => a.stop());
  }, [active]);

  const color = isUser ? '#10b981' : '#667eea';

  return (
    <View style={waveStyles.container}>
      {bars.map((anim, i) => (
        <Animated.View
          key={i}
          style={[
            waveStyles.bar,
            { backgroundColor: active ? color : '#333', transform: [{ scaleY: anim }] },
          ]}
        />
      ))}
    </View>
  );
}

// ─── Status indicator ───────────────────────────────────────────────────────

function StatusIndicator({ state, isUserSpeaking }) {
  const config = {
    connecting: { color: '#f59e0b', text: 'Connecting...' },
    listening: { color: '#10b981', text: isUserSpeaking ? 'You are speaking...' : 'Listening...' },
    speaking: { color: '#667eea', text: 'Lia is speaking...' },
    idle: { color: '#666', text: 'Ready to talk' },
  };
  const { color, text } = config[state] || config.idle;
  return (
    <View style={statusStyles.row}>
      <View style={[statusStyles.dot, { backgroundColor: color }]} />
      <Text style={[statusStyles.text, { color }]}>{text}</Text>
    </View>
  );
}

// ─── VoiceControls (must live inside <LiveKitRoom>) ─────────────────────────

function VoiceControls({ onDisconnect }) {
  const room = useRoomContext();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const remoteParticipants = useRemoteParticipants();

  const [messages, setMessages] = useState([]);
  const [currentUserTranscript, setCurrentUserTranscript] = useState('');
  const [currentAgentTranscript, setCurrentAgentTranscript] = useState('');

  const flatListRef = useRef(null);

  // Derive agent participant and speaking states
  const agentParticipant = remoteParticipants.find(
    (p) => p.identity?.includes('agent') || p.identity?.includes('assistant')
  );
  const isAgentSpeaking = agentParticipant?.isSpeaking ?? false;
  const isUserSpeaking = localParticipant?.isSpeaking ?? false;

  const agentState = (() => {
    if (!agentParticipant) return 'connecting';
    if (isAgentSpeaking) return 'speaking';
    if (isUserSpeaking) return 'listening';
    return 'idle';
  })();

  // Transcription events
  useEffect(() => {
    if (!room) return;

    const handleTranscription = (transcriptions) => {
      transcriptions.forEach(({ segments, participant }) => {
        segments.forEach((segment) => {
          const text = segment.text?.trim();
          if (!text) return;
          const isAgent =
            participant?.identity?.includes('agent') ||
            participant?.identity?.includes('assistant');

          if (segment.final) {
            setMessages((prev) => [...prev, { type: isAgent ? 'ai' : 'user', text }]);
            if (isAgent) setCurrentAgentTranscript('');
            else setCurrentUserTranscript('');
          } else {
            if (isAgent) setCurrentAgentTranscript(text);
            else setCurrentUserTranscript(text);
          }
        });
      });
    };

    room.on(RoomEvent.TranscriptionReceived, handleTranscription);
    return () => room.off(RoomEvent.TranscriptionReceived, handleTranscription);
  }, [room]);

  // Data channel messages (fallback for agents that send data instead of transcription)
  useEffect(() => {
    if (!room) return;

    const handleData = (payload) => {
      try {
        let text;
        try {
          text = new TextDecoder().decode(payload);
        } catch {
          text = String.fromCharCode(...Array.from(new Uint8Array(payload)));
        }
        const data = JSON.parse(text);
        if (data.type === 'transcript' && data.text) {
          setMessages((prev) => [
            ...prev,
            { type: data.role === 'assistant' ? 'ai' : 'user', text: data.text },
          ]);
        }
      } catch { /* ignore malformed */ }
    };

    room.on(RoomEvent.DataReceived, handleData);
    return () => room.off(RoomEvent.DataReceived, handleData);
  }, [room]);

  // Build display list: finalized messages + in-progress transcripts
  const displayMessages = [
    ...messages,
    ...(currentUserTranscript
      ? [{ type: 'user', text: currentUserTranscript, typing: true }]
      : []),
    ...(currentAgentTranscript
      ? [{ type: 'ai', text: currentAgentTranscript, typing: true }]
      : []),
  ];

  const toggleMic = async () => {
    if (localParticipant) {
      await localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled);
    }
  };

  const renderMessage = ({ item, index }) => (
    <View
      key={index}
      style={[
        styles.message,
        item.type === 'user' ? styles.userMessage : styles.aiMessage,
        item.typing && styles.typingMessage,
      ]}
    >
      <Text style={styles.messageAvatar}>{item.type === 'user' ? '👤' : '🤖'}</Text>
      <Text style={styles.messageText}>
        {item.text}
        {item.typing ? <Text style={styles.cursor}>|</Text> : null}
      </Text>
    </View>
  );

  return (
    <View style={styles.conversationBox}>
      {/* Header */}
      <View style={styles.conversationHeader}>
        <Text style={styles.conversationTitle}>Conversation with Lia</Text>
        <StatusIndicator state={agentState} isUserSpeaking={isUserSpeaking} />
      </View>

      {/* Messages */}
      <FlatList
        ref={flatListRef}
        data={displayMessages}
        keyExtractor={(_, i) => String(i)}
        renderItem={renderMessage}
        onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
        style={styles.messagesList}
        contentContainerStyle={styles.messagesContent}
        ListEmptyComponent={
          <View style={styles.emptyState}>
            <WaveformDisplay
              active={isAgentSpeaking || isUserSpeaking}
              isUser={isUserSpeaking}
            />
            {(isAgentSpeaking || isUserSpeaking) && (
              <Text style={styles.waveLabel}>
                {isUserSpeaking ? '🎤 You are speaking' : '🤖 Lia is speaking'}
              </Text>
            )}
            {!isAgentSpeaking && !isUserSpeaking && (
              <Text style={styles.emptyHint}>
                Start speaking to begin your conversation
              </Text>
            )}
          </View>
        }
      />

      {/* Controls */}
      <View style={styles.controls}>
        <TouchableOpacity
          style={[
            styles.controlBtn,
            isMicrophoneEnabled ? styles.micActive : styles.micMuted,
          ]}
          onPress={toggleMic}
          activeOpacity={0.8}
        >
          <Text style={styles.controlBtnIcon}>{isMicrophoneEnabled ? '🎤' : '🔇'}</Text>
          <Text style={styles.controlBtnLabel}>
            {isMicrophoneEnabled ? 'Mute' : 'Unmute'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.controlBtn, styles.disconnectBtn]}
          onPress={onDisconnect}
          activeOpacity={0.8}
        >
          <Text style={styles.controlBtnIcon}>✕</Text>
          <Text style={styles.controlBtnLabel}>End</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ─── VoiceScreen (outer) ────────────────────────────────────────────────────

export default function VoiceScreen({ navigation }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [livekitUrl, setLivekitUrl] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    storage.getItem('user').then((str) => {
      if (str) setUser(JSON.parse(str));
    });
  }, []);

  const requestMicPermission = async () => {
    if (Platform.OS !== 'android') {
      return true;
    }
    const result = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
      {
        title: 'Microphone Permission',
        message: 'Lia needs microphone access for real-time voice conversations.',
        buttonPositive: 'Allow',
        buttonNegative: 'Deny',
      }
    );
    return result === PermissionsAndroid.RESULTS.GRANTED;
  };

  const getToken = useCallback(async () => {
    if (!user) return;
    setIsConnecting(true);
    setError('');

    const granted = await requestMicPermission();
    if (!granted) {
      setError('Microphone permission is required for voice conversations.');
      setIsConnecting(false);
      return;
    }

    try {
      ensureLiveKitGlobals();
      await AudioSession.startAudioSession();
      const response = await api.get('/getToken', {
        params: { name: user.email || 'User' },
      });

      const nextToken = response?.data?.token;
      const nextUrl = response?.data?.url || '';

      if (!nextToken) {
        setError('LiveKit token generation failed. Check backend configuration.');
        setIsConnecting(false);
        return;
      }
      if (!nextUrl.startsWith('ws://') && !nextUrl.startsWith('wss://')) {
        setError('LiveKit URL is missing or invalid. Set LIVEKIT_URL on the backend.');
        setIsConnecting(false);
        return;
      }

      setToken(nextToken);
      setLivekitUrl(nextUrl);
      setIsConnecting(false);
      setIsConnected(true);
    } catch (err) {
      const msg =
        err.response?.data?.error ||
        err.response?.data?.msg ||
        err.message ||
        'Failed to connect. Please try again.';
      setError(msg);
      setIsConnecting(false);
    }
  }, [user]);

  useEffect(() => {
    if (user) getToken();
  }, [user, getToken]);

  const handleDisconnect = async () => {
    setIsConnected(false);
    setToken(null);
    setLivekitUrl('');
    await AudioSession.stopAudioSession();
  };

  const handleLogout = async () => {
    await handleDisconnect();
    await storage.removeItem('token');
    await storage.removeItem('user');
    navigation.replace('Login');
  };

  if (!user) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#667eea" />
      </View>
    );
  }

  const isAdminOrOwner = user.role === 'admin' || user.role === 'owner';

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Lia</Text>
        <View style={styles.headerRight}>
          <Text style={styles.headerUser} numberOfLines={1}>
            {user.name || user.email}
          </Text>
          {isAdminOrOwner && (
            <TouchableOpacity
              style={styles.headerBtn}
              onPress={() => navigation.navigate('ConnectorSettings')}
            >
              <Text style={styles.headerBtnText}>⚙️</Text>
            </TouchableOpacity>
          )}
          {!!error && (
            <TouchableOpacity style={styles.headerBtn} onPress={getToken}>
              <Text style={styles.headerBtnText}>↻</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
            <Text style={styles.logoutBtnText}>Logout</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Content */}
      <View style={styles.content}>
        {!!error && (
          <View style={styles.errorBanner}>
            <Text style={styles.errorBannerText}>{error}</Text>
            <TouchableOpacity onPress={getToken} style={styles.retryBtn}>
              <Text style={styles.retryBtnText}>Retry</Text>
            </TouchableOpacity>
          </View>
        )}

        {isConnecting && !error && (
          <View style={styles.centerContent}>
            <ActivityIndicator size="large" color="#667eea" />
            <Text style={styles.connectingText}>Connecting to Lia...</Text>
          </View>
        )}

        {!isConnecting && !isConnected && !error && (
          <View style={styles.centerContent}>
            <TouchableOpacity style={styles.reconnectBtn} onPress={getToken}>
              <Text style={styles.reconnectBtnText}>Connect to Lia</Text>
            </TouchableOpacity>
          </View>
        )}

        {isConnected && !!token && !!livekitUrl && (
          <LiveKitRoom
            serverUrl={livekitUrl}
            token={token}
            connect
            audio
            video={false}
            onDisconnected={handleDisconnect}
            options={{ adaptiveStream: true, dynacast: true }}
            style={styles.flex}
          >
            <VoiceControls onDisconnect={handleDisconnect} />
          </LiveKitRoom>
        )}
      </View>
    </SafeAreaView>
  );
}
