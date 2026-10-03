import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const lk = vi.hoisted(() => ({
  state: 'listening',
  micEnabled: true,
  dataHandler: null,
  roomHandlers: {},
  room: null,
}));

vi.mock('@livekit/components-styles', () => ({}));
vi.mock('livekit-client', () => ({ RoomEvent: { TranscriptionReceived: 'transcription' } }));
vi.mock('@livekit/components-react', () => ({
  LiveKitRoom: ({ children }) => <div data-testid="room">{children}</div>,
  RoomAudioRenderer: () => null,
  useVoiceAssistant: () => ({ state: lk.state }),
  useRoomContext: () => lk.room,
  useDataChannel: (cb) => {
    lk.dataHandler = cb;
  },
  useLocalParticipant: () => ({ isMicrophoneEnabled: lk.micEnabled, microphoneTrack: null }),
}));
vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal()),
  api: { get: vi.fn() },
}));

import { api } from '../lib/api';
import VoiceInterface from './VoiceInterface';

const account = { email: 'u@x.co', role: 'user' };
const goodToken = { data: { token: 'lk-token', room: 'room-1', url: 'wss://lk.example.com' } };

beforeEach(() => {
  vi.clearAllMocks();
  lk.state = 'listening';
  lk.micEnabled = true;
  lk.roomHandlers = {};
  lk.room = {
    on: (evt, cb) => {
      lk.roomHandlers[evt] = cb;
    },
    off: vi.fn(),
    localParticipant: { setMicrophoneEnabled: vi.fn().mockResolvedValue(undefined) },
    switchActiveDevice: vi.fn().mockResolvedValue(undefined),
  };
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      enumerateDevices: vi.fn().mockResolvedValue([
        { kind: 'audioinput', deviceId: 'm1', label: 'Built-in mic' },
        { kind: 'audioinput', deviceId: 'm2', label: '' },
        { kind: 'videoinput', deviceId: 'c1', label: 'Camera' },
      ]),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    },
  });
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
});

describe('VoiceInterface', () => {
  it('shows a connecting state, then the conversation', async () => {
    api.get.mockResolvedValue(goodToken);
    render(<VoiceInterface user={account} onLogout={() => {}} onOpenConnectorSettings={() => {}} />);
    expect(screen.getByText('Connecting to Lia...')).toBeInTheDocument();
    expect(await screen.findByTestId('room')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/getToken', { params: { name: 'u@x.co' } });
    expect(screen.getByRole('status')).toHaveTextContent('Listening...');
    expect(screen.queryByRole('button', { name: /settings/i })).not.toBeInTheDocument();
  });

  it('never logs the token response', async () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    api.get.mockResolvedValue(goodToken);
    render(<VoiceInterface user={account} onLogout={() => {}} />);
    await screen.findByTestId('room');
    expect(log).not.toHaveBeenCalled();
    log.mockRestore();
  });

  it('shows settings for admins and supports logout', async () => {
    const u = userEvent.setup();
    api.get.mockResolvedValue(goodToken);
    const onLogout = vi.fn();
    const onOpenConnectorSettings = vi.fn();
    render(
      <VoiceInterface user={{ ...account, role: 'admin' }} onLogout={onLogout} onOpenConnectorSettings={onOpenConnectorSettings} />,
    );
    await screen.findByTestId('room');
    await u.click(screen.getByRole('button', { name: /settings/i }));
    await u.click(screen.getByRole('button', { name: /log out/i }));
    expect(onOpenConnectorSettings).toHaveBeenCalled();
    expect(onLogout).toHaveBeenCalled();
  });

  it('shows an error with a reconnect action when the token request fails', async () => {
    const u = userEvent.setup();
    api.get.mockRejectedValueOnce({ response: { data: { error: 'Service unavailable' } } });
    api.get.mockResolvedValueOnce(goodToken);
    render(<VoiceInterface user={account} onLogout={() => {}} />);
    expect(await screen.findByText('Service unavailable')).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: /reconnect/i }));
    expect(await screen.findByTestId('room')).toBeInTheDocument();
  });

  it('rejects a response without token or with an invalid LiveKit URL', async () => {
    api.get.mockResolvedValueOnce({ data: {} });
    const { unmount } = render(<VoiceInterface user={account} onLogout={() => {}} />);
    expect(await screen.findByText(/token generation failed/i)).toBeInTheDocument();
    unmount();

    api.get.mockResolvedValueOnce({ data: { token: 't', room: 'r', url: 'http://nope' } });
    render(<VoiceInterface user={account} onLogout={() => {}} />);
    expect(await screen.findByText(/LiveKit URL is missing or invalid/i)).toBeInTheDocument();
  });

  it('can disconnect and connect again', async () => {
    const u = userEvent.setup();
    api.get.mockResolvedValue(goodToken);
    render(<VoiceInterface user={account} onLogout={() => {}} />);
    await screen.findByTestId('room');

    await u.click(screen.getByRole('button', { name: 'Disconnect' }));
    expect(screen.getByRole('heading', { name: 'Disconnected from Lia' })).toBeInTheDocument();
    await u.click(screen.getByRole('button', { name: 'Connect' }));
    expect(await screen.findByTestId('room')).toBeInTheDocument();
  });

  it('toggles the microphone with an accessible pressed state', async () => {
    const u = userEvent.setup();
    api.get.mockResolvedValue(goodToken);
    render(<VoiceInterface user={account} onLogout={() => {}} />);
    await screen.findByTestId('room');

    const mic = screen.getByRole('button', { name: 'Mute microphone' });
    expect(mic).toHaveAttribute('aria-pressed', 'false');
    await u.click(mic);
    expect(lk.room.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(false);
  });

  it('lists microphones, switches device and closes with Escape', async () => {
    const u = userEvent.setup();
    api.get.mockResolvedValue(goodToken);
    render(<VoiceInterface user={account} onLogout={() => {}} />);
    await screen.findByTestId('room');
    await waitFor(() => expect(navigator.mediaDevices.enumerateDevices).toHaveBeenCalled());

    const picker = screen.getByRole('button', { name: 'Select microphone' });
    expect(picker).toHaveAttribute('aria-expanded', 'false');
    await u.click(picker);
    expect(picker).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByRole('button', { name: /Built-in mic/ })).toHaveAttribute('aria-pressed', 'true');

    await u.click(screen.getByRole('button', { name: 'Microphone 2' }));
    expect(lk.room.switchActiveDevice).toHaveBeenCalledWith('audioinput', 'm2');
    expect(screen.queryByRole('group', { name: 'Microphones' })).not.toBeInTheDocument();

    await u.click(picker);
    await u.keyboard('{Escape}');
    expect(screen.queryByRole('group', { name: 'Microphones' })).not.toBeInTheDocument();
  });

  it('renders transcripts from the data channel and from room events', async () => {
    api.get.mockResolvedValue(goodToken);
    render(<VoiceInterface user={account} onLogout={() => {}} />);
    await screen.findByTestId('room');

    act(() => {
      lk.dataHandler({ payload: JSON.stringify({ type: 'transcript', role: 'assistant', text: 'Hello there' }) });
      lk.dataHandler({ payload: 'not json' });
    });
    const log = screen.getByRole('log', { name: 'Conversation transcript' });
    expect(log).toHaveTextContent('Hello there');

    act(() => {
      lk.roomHandlers.transcription(
        [{ participant: { identity: 'user-1' }, segments: [{ text: 'partial words', final: false }] }],
      );
    });
    expect(log).toHaveTextContent('partial words');
    act(() => {
      lk.roomHandlers.transcription(
        [{ participant: { identity: 'user-1' }, segments: [{ text: 'final words', final: true }] }],
      );
    });
    expect(log).toHaveTextContent('final words');
    expect(log).not.toHaveTextContent('partial words');

    act(() => {
      lk.roomHandlers.transcription(
        [{ participant: { identity: 'agent-1' }, segments: [{ text: 'agent typing', final: false }] }],
      );
    });
    expect(log).toHaveTextContent('agent typing');
  });

  it.each([
    ['connecting', 'Connecting...'],
    ['thinking', 'Lia is thinking...'],
    ['speaking', 'Lia is speaking...'],
    ['idle', 'Ready to talk'],
  ])('announces the %s state', async (state, text) => {
    lk.state = state;
    api.get.mockResolvedValue(goodToken);
    render(<VoiceInterface user={account} onLogout={() => {}} />);
    await screen.findByTestId('room');
    expect(screen.getByRole('status')).toHaveTextContent(text);
  });
});
