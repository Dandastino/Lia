import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('./components/Admin', () => ({
  default: ({ user, onLogout }) => (
    <div>
      <p>admin view for {user.email}</p>
      <button onClick={onLogout}>Log out</button>
    </div>
  ),
}));
vi.mock('./components/VoiceInterface', () => ({
  default: ({ user, onLogout, onOpenConnectorSettings }) => (
    <div>
      <p>voice view for {user.email}</p>
      <button onClick={onOpenConnectorSettings}>Settings</button>
      <button onClick={onLogout}>Log out</button>
    </div>
  ),
}));
vi.mock('./components/ConnectorSettings', () => ({
  default: ({ onBack }) => <button onClick={onBack}>Back</button>,
}));
vi.mock('./components/Login', () => ({
  default: ({ onLoginSuccess }) => (
    <button onClick={() => onLoginSuccess({ email: 'new@x.co', role: 'admin' })}>fake login</button>
  ),
}));

import App from './App';
import { UNAUTHORIZED_EVENT } from './lib/api';

const signIn = (user) => {
  localStorage.setItem('token', 'tok');
  localStorage.setItem('user', JSON.stringify(user));
};

describe('App routing', () => {
  beforeEach(() => localStorage.clear());

  it('shows the login screen without a session', () => {
    render(<App />);
    expect(screen.getByText('fake login')).toBeInTheDocument();
    expect(document.title).toBe('Sign in - Lia');
  });

  it.each(['admin', 'owner'])('routes %s users to the admin panel', (role) => {
    signIn({ email: 'a@x.co', role });
    render(<App />);
    expect(screen.getByText('admin view for a@x.co')).toBeInTheDocument();
  });

  it('routes regular users to the assistant, and to settings and back', async () => {
    const user = userEvent.setup();
    signIn({ email: 'u@x.co', role: 'user' });
    render(<App />);
    expect(await screen.findByText('voice view for u@x.co')).toBeInTheDocument();

    await user.click(screen.getByText('Settings'));
    await user.click(await screen.findByText('Back'));
    expect(await screen.findByText('voice view for u@x.co')).toBeInTheDocument();
  });

  it('falls back to login when the stored user is corrupted', () => {
    localStorage.setItem('token', 'tok');
    localStorage.setItem('user', '{broken');
    render(<App />);
    expect(screen.getByText('fake login')).toBeInTheDocument();
  });

  it('routes after a successful login and logs out', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByText('fake login'));
    expect(screen.getByText('admin view for new@x.co')).toBeInTheDocument();
    await user.click(screen.getByText('Log out'));
    expect(screen.getByText('fake login')).toBeInTheDocument();
    expect(localStorage.getItem('token')).toBeNull();
  });

  it('logs out when the API reports an expired session', () => {
    signIn({ email: 'a@x.co', role: 'admin' });
    render(<App />);
    expect(screen.getByText('admin view for a@x.co')).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    });
    expect(screen.getByText('fake login')).toBeInTheDocument();
    expect(localStorage.getItem('token')).toBeNull();
  });
});
