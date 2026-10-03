import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  UNAUTHORIZED_EVENT,
  attachAuthHeader,
  getErrorMessage,
  handleResponseError,
  resolveBaseURL,
} from './api';

describe('resolveBaseURL', () => {
  it('falls back to the dev proxy prefix', () => {
    expect(resolveBaseURL('')).toBe('/api');
    expect(resolveBaseURL(undefined)).toBe('/api');
  });

  it('uses VITE_API_URL and trims trailing slashes', () => {
    expect(resolveBaseURL('https://host/api///')).toBe('https://host/api');
    expect(resolveBaseURL(' http://localhost:5000 ')).toBe('http://localhost:5000');
  });
});

describe('attachAuthHeader', () => {
  beforeEach(() => localStorage.clear());

  it('adds the bearer token when present', () => {
    localStorage.setItem('token', 'abc');
    expect(attachAuthHeader({ headers: {} }).headers.Authorization).toBe('Bearer abc');
  });

  it('adds nothing without a token', () => {
    expect(attachAuthHeader({ headers: {} }).headers.Authorization).toBeUndefined();
  });
});

describe('handleResponseError', () => {
  beforeEach(() => localStorage.clear());

  it('clears the session and notifies the app on 401', async () => {
    localStorage.setItem('token', 'abc');
    localStorage.setItem('user', '{}');
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);

    const error = { response: { status: 401 }, config: { url: '/admin/dashboard' } };
    await expect(handleResponseError(error)).rejects.toBe(error);

    expect(localStorage.getItem('token')).toBeNull();
    expect(localStorage.getItem('user')).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  });

  it('does not log out when the login request itself returns 401', async () => {
    localStorage.setItem('token', 'abc');
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);

    const error = { response: { status: 401 }, config: { url: '/login' } };
    await expect(handleResponseError(error)).rejects.toBe(error);

    expect(localStorage.getItem('token')).toBe('abc');
    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  });

  it('passes other errors through untouched', async () => {
    const error = { response: { status: 500 }, config: { url: '/x' } };
    await expect(handleResponseError(error)).rejects.toBe(error);
  });
});

describe('getErrorMessage', () => {
  it('prefers the server error field', () => {
    expect(getErrorMessage({ response: { data: { error: 'Nope' } } })).toBe('Nope');
  });

  it('supports the msg field', () => {
    expect(getErrorMessage({ response: { data: { msg: 'Token expired' } } })).toBe('Token expired');
  });

  it('uses the fallback for responses without a message', () => {
    expect(getErrorMessage({ response: { data: '<html>' } }, 'Fallback')).toBe('Fallback');
  });

  it('explains network failures', () => {
    expect(getErrorMessage({ request: {} })).toMatch(/cannot reach the server/i);
  });

  it('falls back for unknown errors', () => {
    expect(getErrorMessage(new Error('boom'), 'Fallback')).toBe('Fallback');
  });
});
