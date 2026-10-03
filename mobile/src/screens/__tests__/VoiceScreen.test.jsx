import { AccessibilityInfo, PermissionsAndroid, Platform } from 'react-native';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AudioSession } from '@livekit/react-native';
import VoiceScreen from '../VoiceScreen';
import { api } from '../../lib/api';

jest.mock('../../lib/api', () => ({
  ...jest.requireActual('../../lib/api'),
  api: { get: jest.fn() },
}));

// The LiveKit native modules cannot run in Jest: replace them with a controllable fake.
const mockState = {
  roomProps: null,
  micEnabled: true,
  localParticipant: null,
  remote: [],
  listeners: {},
};
const mockRoom = {
  on: (event, cb) => {
    (mockState.listeners[event] = mockState.listeners[event] || new Set()).add(cb);
  },
  off: (event, cb) => mockState.listeners[event]?.delete(cb),
};
const mockEmit = (event, payload) => (mockState.listeners[event] || []).forEach((cb) => cb(payload));

jest.mock('@livekit/react-native', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    registerGlobals: jest.fn(),
    AudioSession: { startAudioSession: jest.fn(), stopAudioSession: jest.fn() },
    LiveKitRoom: ({ children, ...props }) => {
      mockState.roomProps = props;
      return React.createElement(View, { testID: 'livekit-room' }, children);
    },
    useRoomContext: () => mockRoom,
    useLocalParticipant: () => ({
      localParticipant: mockState.localParticipant,
      isMicrophoneEnabled: mockState.micEnabled,
    }),
    useRemoteParticipants: () => mockState.remote,
  };
});

jest.mock('livekit-client', () => ({
  RoomEvent: { TranscriptionReceived: 'transcription', DataReceived: 'data' },
}));

const USER = { id: '1', email: 'bob@acme.com', role: 'user' };
const flush = () => act(async () => {});

async function setup(user = USER) {
  if (user) await AsyncStorage.setItem('user', JSON.stringify(user));
  const navigation = { replace: jest.fn(), navigate: jest.fn() };
  render(<VoiceScreen navigation={navigation} />);
  await flush();
  return navigation;
}

const press = (name) => fireEvent.press(screen.getByRole('button', { name }));

describe('VoiceScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockState.roomProps = null;
    mockState.micEnabled = true;
    mockState.remote = [];
    mockState.listeners = {};
    mockState.localParticipant = { isSpeaking: false, setMicrophoneEnabled: jest.fn().mockResolvedValue() };
    api.get.mockResolvedValue({ data: { token: 'lk-token', url: 'wss://lk.example.com' } });
    jest.spyOn(AccessibilityInfo, 'announceForAccessibility').mockImplementation(() => {});
  });

  afterEach(() => jest.restoreAllMocks());

  describe('token fetch', () => {
    it('fetches a LiveKit token for the signed-in user and joins the room', async () => {
      await setup();
      expect(AudioSession.startAudioSession).toHaveBeenCalled();
      expect(api.get).toHaveBeenCalledWith('/getToken', { params: { name: 'bob@acme.com' } });
      expect(mockState.roomProps).toMatchObject({ serverUrl: 'wss://lk.example.com', token: 'lk-token', audio: true, video: false });
      expect(screen.getByText('Conversation with Lia')).toBeOnTheScreen();
    });

    it('shows a loading state while no user is available yet', async () => {
      render(<VoiceScreen navigation={{ replace: jest.fn() }} />);
      expect(screen.getByLabelText('Loading')).toBeOnTheScreen();
      await flush();
      expect(api.get).not.toHaveBeenCalled();
    });

    it('shows the backend error as an alert and offers retry', async () => {
      api.get.mockRejectedValueOnce({ response: { data: { error: 'LiveKit is not configured' } } });
      await setup();
      expect(screen.getByText('LiveKit is not configured')).toBeOnTheScreen();
      expect(screen.getByRole('alert').props.accessibilityLiveRegion).toBe('assertive');
      expect(screen.queryByTestId('livekit-room')).toBeNull();

      press('Retry');
      await flush();
      expect(screen.queryByText('LiveKit is not configured')).toBeNull();
      expect(screen.getByTestId('livekit-room')).toBeOnTheScreen();
      expect(api.get).toHaveBeenCalledTimes(2);
    });

    it('reports an unreachable server', async () => {
      api.get.mockRejectedValueOnce({ request: {} });
      await setup();
      expect(screen.getByText(/Cannot reach the server/)).toBeOnTheScreen();
    });

    it('can retry from the header too', async () => {
      api.get.mockRejectedValueOnce(new Error('x'));
      await setup();
      press('Retry connecting');
      await flush();
      expect(screen.getByTestId('livekit-room')).toBeOnTheScreen();
    });

    it('rejects a response without a token', async () => {
      api.get.mockResolvedValue({ data: { url: 'wss://lk.example.com' } });
      await setup();
      expect(screen.getByText(/token generation failed/)).toBeOnTheScreen();
      expect(screen.queryByTestId('livekit-room')).toBeNull();
    });

    it('rejects a response with a missing or non-websocket URL', async () => {
      api.get.mockResolvedValue({ data: { token: 't', url: 'https://lk.example.com' } });
      await setup();
      expect(screen.getByText(/LiveKit URL is missing or invalid/)).toBeOnTheScreen();
    });

    it('does not fetch a token when Android microphone permission is denied', async () => {
      const original = Platform.OS;
      Platform.OS = 'android';
      jest.spyOn(PermissionsAndroid, 'request').mockResolvedValue(PermissionsAndroid.RESULTS.DENIED);
      try {
        await setup();
        expect(screen.getByText('Microphone permission is required for voice conversations.')).toBeOnTheScreen();
        expect(api.get).not.toHaveBeenCalled();
      } finally {
        Platform.OS = original;
      }
    });

    it('asks for the Android microphone permission and connects when granted', async () => {
      const original = Platform.OS;
      Platform.OS = 'android';
      const request = jest.spyOn(PermissionsAndroid, 'request').mockResolvedValue(PermissionsAndroid.RESULTS.GRANTED);
      try {
        await setup();
        expect(request).toHaveBeenCalled();
        expect(screen.getByTestId('livekit-room')).toBeOnTheScreen();
      } finally {
        Platform.OS = original;
      }
    });
  });

  describe('reconnect', () => {
    it('ends the call, offers to reconnect and fetches a fresh token', async () => {
      await setup();
      press('End conversation');
      await flush();
      expect(AudioSession.stopAudioSession).toHaveBeenCalled();
      expect(screen.queryByTestId('livekit-room')).toBeNull();

      press('Connect to Lia');
      await flush();
      expect(api.get).toHaveBeenCalledTimes(2);
      expect(screen.getByTestId('livekit-room')).toBeOnTheScreen();
    });

    it('treats a server-side disconnect like ending the call', async () => {
      await setup();
      await act(async () => mockState.roomProps.onDisconnected());
      expect(screen.getByRole('button', { name: 'Connect to Lia' })).toBeOnTheScreen();
    });
  });

  describe('microphone', () => {
    it('exposes the mic as a switch that is on and mutes when pressed', async () => {
      await setup();
      const mic = screen.getByRole('switch', { name: 'Microphone' });
      expect(mic.props.accessibilityState.checked).toBe(true);
      expect(mic.props.accessibilityHint).toBe('Double tap to mute');
      expect(screen.getByText('Mute')).toBeOnTheScreen();

      fireEvent.press(mic);
      await flush();
      expect(mockState.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(false);
      expect(AccessibilityInfo.announceForAccessibility).toHaveBeenCalledWith('Microphone muted');
    });

    it('shows the muted state and unmutes when pressed', async () => {
      mockState.micEnabled = false;
      await setup();
      const mic = screen.getByRole('switch', { name: 'Microphone' });
      expect(mic.props.accessibilityState.checked).toBe(false);
      expect(mic.props.accessibilityHint).toBe('Double tap to unmute');
      expect(screen.getByText('Unmute')).toBeOnTheScreen();

      fireEvent.press(mic);
      await flush();
      expect(mockState.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(true);
      expect(AccessibilityInfo.announceForAccessibility).toHaveBeenCalledWith('Microphone on');
    });

    it('announces when the microphone cannot be changed', async () => {
      await setup();
      mockState.localParticipant.setMicrophoneEnabled.mockRejectedValue(new Error('denied'));
      fireEvent.press(screen.getByRole('switch', { name: 'Microphone' }));
      await flush();
      expect(AccessibilityInfo.announceForAccessibility).toHaveBeenCalledWith('Could not change the microphone state');
    });

    it('does nothing without a local participant', async () => {
      mockState.localParticipant = null;
      await setup();
      fireEvent.press(screen.getByRole('switch', { name: 'Microphone' }));
      await flush();
      expect(AccessibilityInfo.announceForAccessibility).not.toHaveBeenCalled();
    });
  });

  describe('conversation', () => {
    it('announces the status as a live region', async () => {
      await setup();
      const status = screen.getByLabelText('Status: Connecting...');
      expect(status.props.accessibilityLiveRegion).toBe('polite');
    });

    it.each([
      [{ identity: 'agent-1', isSpeaking: true }, false, 'Status: Lia is speaking...'],
      [{ identity: 'agent-1', isSpeaking: false }, true, 'Status: You are speaking...'],
      [{ identity: 'assistant', isSpeaking: false }, false, 'Status: Ready to talk'],
    ])('derives the status from participants (%#)', async (agent, userSpeaking, label) => {
      mockState.remote = [{ identity: 'someone' }, agent];
      mockState.localParticipant.isSpeaking = userSpeaking;
      await setup();
      expect(screen.getByLabelText(label)).toBeOnTheScreen();
    });

    it('renders final and in-progress transcriptions', async () => {
      await setup();
      expect(screen.getByText('Start speaking to begin your conversation')).toBeOnTheScreen();
      await act(async () =>
        mockEmit('transcription', [
          { participant: { identity: 'agent-1' }, segments: [{ text: ' Hello there ', final: true }, { text: '  ' }] },
          { participant: { identity: 'bob' }, segments: [{ text: 'Hi Li', final: false }] },
        ]),
      );
      expect(screen.getByLabelText('Lia: Hello there')).toBeOnTheScreen();
      expect(screen.getByLabelText('You: Hi Li')).toBeOnTheScreen();

      await act(async () =>
        mockEmit('transcription', [{ participant: { identity: 'bob' }, segments: [{ text: 'Hi Lia', final: true }] }]),
      );
      expect(screen.getByLabelText('You: Hi Lia')).toBeOnTheScreen();
      expect(screen.queryByLabelText('You: Hi Li')).toBeNull();

      await act(async () =>
        mockEmit('transcription', [{ participant: { identity: 'agent-1' }, segments: [{ text: 'typing', final: false }] }]),
      );
      expect(screen.getByLabelText('Lia: typing')).toBeOnTheScreen();
    });

    it('accepts transcript messages from the data channel and ignores malformed ones', async () => {
      await setup();
      const encode = (value) => new TextEncoder().encode(typeof value === 'string' ? value : JSON.stringify(value));
      await act(async () => mockEmit('data', encode({ type: 'transcript', role: 'assistant', text: 'From data' })));
      await act(async () => mockEmit('data', encode('not json')));
      await act(async () => mockEmit('data', encode({ type: 'other' })));
      expect(screen.getByLabelText('Lia: From data')).toBeOnTheScreen();
    });

    it('shows the speaking label in the empty state', async () => {
      mockState.remote = [{ identity: 'agent-1', isSpeaking: true }];
      await setup();
      expect(screen.getAllByText(/Lia is speaking/).length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('header', () => {
    it('shows the connector settings button to admins and owners only', async () => {
      const navigation = await setup({ ...USER, role: 'owner' });
      press('Connector settings');
      expect(navigation.navigate).toHaveBeenCalledWith('ConnectorSettings');
    });

    it('hides connector settings from regular users', async () => {
      await setup();
      expect(screen.queryByRole('button', { name: 'Connector settings' })).toBeNull();
      expect(screen.getByText('bob@acme.com')).toBeOnTheScreen();
    });

    it('logout ends the audio session, clears storage and returns to Login', async () => {
      await AsyncStorage.setItem('token', 'jwt');
      const navigation = await setup();
      press('Logout');
      await flush();
      expect(AudioSession.stopAudioSession).toHaveBeenCalled();
      expect(await AsyncStorage.getItem('token')).toBeNull();
      expect(await AsyncStorage.getItem('user')).toBeNull();
      expect(navigation.replace).toHaveBeenCalledWith('Login');
    });
  });
});
