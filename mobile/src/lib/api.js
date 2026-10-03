import axios from 'axios';
import { clearSession, getToken } from './storage';

// Backend base URL. Set EXPO_PUBLIC_API_URL at build time (see README / eas.json).
// When it is missing we fall back to http://localhost:5000 (the backend dev
// default) instead of crashing at import time. Note: on a physical device or the
// Android emulator "localhost" is the device itself, so set the variable to your
// machine's LAN address (or 10.0.2.2 for the Android emulator).
export const DEFAULT_API_URL = 'http://localhost:5000';

export function resolveBaseURL(envValue = process.env.EXPO_PUBLIC_API_URL) {
  const value = typeof envValue === 'string' ? envValue.trim() : '';
  return (value || DEFAULT_API_URL).replace(/\/+$/, '');
}

export const api = axios.create({
  baseURL: resolveBaseURL(),
  headers: { 'Content-Type': 'application/json' },
});

// Simple subscription so the navigator can react to an expired session.
const unauthorizedListeners = new Set();

export function onUnauthorized(listener) {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export async function attachAuthHeader(config) {
  const token = await getToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}

// A 401 on any endpoint except /login means the session expired or is invalid:
// drop it and tell the app to go back to the Login screen.
export async function handleResponseError(error) {
  const status = error?.response?.status;
  const url = error?.config?.url || '';
  if (status === 401 && !url.endsWith('/login')) {
    await clearSession();
    unauthorizedListeners.forEach((listener) => listener());
  }
  return Promise.reject(error);
}

api.interceptors.request.use(attachAuthHeader);
api.interceptors.response.use((response) => response, handleResponseError);

// Backend errors look like {"error": "..."} (some libraries use {"msg": "..."}).
export function getErrorMessage(err, fallback = 'Something went wrong. Please try again.') {
  if (err?.response) {
    const data = err.response.data;
    if (data && typeof data === 'object') {
      const msg = data.error || data.msg;
      if (typeof msg === 'string' && msg) return msg;
    }
    return fallback;
  }
  if (err?.request) {
    return 'Cannot reach the server. Check your connection and try again.';
  }
  return fallback;
}
