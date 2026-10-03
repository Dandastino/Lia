import axios from 'axios';
import { clearSession, getToken } from './storage';

export const UNAUTHORIZED_EVENT = 'lia:unauthorized';

// VITE_API_URL is set at build time (e.g. https://host/api in production or
// http://localhost:5000). Without it we use "/api", which the Vite dev proxy
// forwards to the backend (see vite.config.js).
export function resolveBaseURL(envValue = import.meta.env.VITE_API_URL) {
  const value = typeof envValue === 'string' ? envValue.trim() : '';
  return value ? value.replace(/\/+$/, '') : '/api';
}

export const api = axios.create({
  baseURL: resolveBaseURL(),
  headers: { 'Content-Type': 'application/json' },
});

export function attachAuthHeader(config) {
  const token = getToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}

// A 401 on any endpoint except /login means the session expired or is invalid:
// drop it and tell the app to go back to the login screen.
export function handleResponseError(error) {
  const status = error?.response?.status;
  const url = error?.config?.url || '';
  if (status === 401 && !url.endsWith('/login')) {
    clearSession();
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
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
