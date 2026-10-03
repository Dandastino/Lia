import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal()),
  api: { post: vi.fn() },
}));

import { api } from '../lib/api';
import Login from './Login';

describe('Login', () => {
  beforeEach(() => vi.clearAllMocks());

  it('has labelled fields and a submit button', () => {
    render(<Login onLoginSuccess={() => {}} />);
    expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    expect(screen.getByRole('main')).toBeInTheDocument();
  });

  it('shows validation messages and does not call the API', async () => {
    const user = userEvent.setup();
    render(<Login onLoginSuccess={() => {}} />);

    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByText('Enter your email address.')).toBeInTheDocument();
    expect(screen.getByText('Enter your password.')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toHaveFocus();
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true');

    await user.type(screen.getByLabelText('Email'), 'not-an-email');
    expect(screen.queryByText('Enter your email address.')).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Password'), 'pw');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByText(/enter a valid email/i)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('focuses the password field when only the password is missing', async () => {
    const user = userEvent.setup();
    render(<Login onLoginSuccess={() => {}} />);
    await user.type(screen.getByLabelText('Email'), 'a@b.co');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByLabelText('Password')).toHaveFocus();
  });

  it('stores the session and reports success', async () => {
    const user = userEvent.setup();
    const onLoginSuccess = vi.fn();
    const account = { email: 'a@b.co', role: 'user' };
    api.post.mockResolvedValue({ data: { access_token: 'tok', user: account } });
    render(<Login onLoginSuccess={onLoginSuccess} />);

    await user.type(screen.getByLabelText('Email'), ' a@b.co ');
    await user.type(screen.getByLabelText('Password'), 'secret1');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(onLoginSuccess).toHaveBeenCalledWith(account));
    expect(api.post).toHaveBeenCalledWith('/login', { email: 'a@b.co', password: 'secret1' });
    expect(localStorage.getItem('token')).toBe('tok');
    expect(JSON.parse(localStorage.getItem('user'))).toEqual(account);
  });

  it('shows the server error for wrong credentials and re-enables the form', async () => {
    const user = userEvent.setup();
    api.post.mockRejectedValue({ response: { status: 401, data: { error: 'Invalid credentials' } } });
    render(<Login onLoginSuccess={vi.fn()} />);

    await user.type(screen.getByLabelText('Email'), 'a@b.co');
    await user.type(screen.getByLabelText('Password'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Invalid credentials')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    expect(localStorage.getItem('token')).toBeNull();
  });

  it('shows a busy state while the request is running', async () => {
    const user = userEvent.setup();
    let resolve;
    api.post.mockReturnValue(new Promise((r) => { resolve = r; }));
    render(<Login onLoginSuccess={vi.fn()} />);

    await user.type(screen.getByLabelText('Email'), 'a@b.co');
    await user.type(screen.getByLabelText('Password'), 'pw');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByRole('button', { name: 'Signing in...' })).toBeDisabled();
    resolve({ data: {} });
    expect(await screen.findByText(/unexpected response/i)).toBeInTheDocument();
  });

  it('reports unreachable servers', async () => {
    const user = userEvent.setup();
    api.post.mockRejectedValue({ request: {} });
    render(<Login onLoginSuccess={vi.fn()} />);
    await user.type(screen.getByLabelText('Email'), 'a@b.co');
    await user.type(screen.getByLabelText('Password'), 'pw');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText(/cannot reach the server/i)).toBeInTheDocument();
  });
});
