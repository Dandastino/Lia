import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, attachAuthHeader, DEFAULT_API_URL, getErrorMessage, handleResponseError, onUnauthorized, resolveBaseURL } from '../api';

// Replace the network layer of the real axios instance with a fake adapter so the
// real interceptors run end to end.
function useAdapter(handler) {
  const calls = [];
  api.defaults.adapter = async (config) => {
    calls.push(config);
    const { status, data } = handler(config);
    const response = { data, status, statusText: '', headers: {}, config, request: {} };
    if (status >= 400) {
      const error = new Error(`Request failed with status code ${status}`);
      error.config = config;
      error.response = response;
      error.isAxiosError = true;
      throw error;
    }
    return response;
  };
  return calls;
}

describe('resolveBaseURL', () => {
  it('falls back to localhost when the env var is undefined or blank', () => {
    expect(resolveBaseURL(undefined)).toBe(DEFAULT_API_URL);
    expect(resolveBaseURL('   ')).toBe('http://localhost:5000');
    expect(resolveBaseURL(42)).toBe('http://localhost:5000');
  });

  it('trims the value and strips trailing slashes', () => {
    expect(resolveBaseURL(' https://api.example.com/api// ')).toBe('https://api.example.com/api');
  });
});

describe('request interceptor', () => {
  it('adds the bearer token when a session exists', async () => {
    await AsyncStorage.setItem('token', 'abc123');
    const calls = useAdapter(() => ({ status: 200, data: {} }));
    await api.get('/ping');
    expect(calls[0].headers.Authorization).toBe('Bearer abc123');
  });

  it('sends no Authorization header without a token', async () => {
    const calls = useAdapter(() => ({ status: 200, data: {} }));
    await api.get('/ping');
    expect(calls[0].headers.Authorization).toBeUndefined();
  });

  it('creates the headers object when it is missing', async () => {
    await AsyncStorage.setItem('token', 't');
    const config = await attachAuthHeader({});
    expect(config.headers.Authorization).toBe('Bearer t');
  });
});

describe('401 handling', () => {
  it('clears the session and notifies listeners on a 401', async () => {
    await AsyncStorage.setItem('token', 'abc');
    await AsyncStorage.setItem('user', '{"id":"1"}');
    const listener = jest.fn();
    const off = onUnauthorized(listener);
    useAdapter(() => ({ status: 401, data: { error: 'expired' } }));

    await expect(api.get('/admin/dashboard')).rejects.toBeTruthy();

    expect(await AsyncStorage.getItem('token')).toBeNull();
    expect(await AsyncStorage.getItem('user')).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    off();
  });

  it('does not treat wrong credentials on /login as an expired session', async () => {
    await AsyncStorage.setItem('token', 'abc');
    const listener = jest.fn();
    const off = onUnauthorized(listener);
    useAdapter(() => ({ status: 401, data: { error: 'Invalid email or password' } }));

    await expect(api.post('/login', {})).rejects.toBeTruthy();

    expect(await AsyncStorage.getItem('token')).toBe('abc');
    expect(listener).not.toHaveBeenCalled();
    off();
  });

  it('passes other errors through untouched and unsubscribes listeners', async () => {
    const listener = jest.fn();
    onUnauthorized(listener)();
    const err = { response: { status: 500 }, config: { url: '/x' } };
    await expect(handleResponseError(err)).rejects.toBe(err);
    await expect(handleResponseError(undefined)).rejects.toBeUndefined();
    expect(listener).not.toHaveBeenCalled();
  });
});

describe('getErrorMessage', () => {
  it('prefers the backend error, then msg', () => {
    expect(getErrorMessage({ response: { data: { error: 'Bad input' } } })).toBe('Bad input');
    expect(getErrorMessage({ response: { data: { msg: 'Token expired' } } })).toBe('Token expired');
  });

  it('uses the fallback for unusable responses', () => {
    expect(getErrorMessage({ response: { data: '<html>' } }, 'Nope')).toBe('Nope');
    expect(getErrorMessage({ response: { data: { error: '' } } })).toMatch(/Something went wrong/);
    expect(getErrorMessage({ response: {} }, 'x')).toBe('x');
  });

  it('reports an unreachable server', () => {
    expect(getErrorMessage({ request: {} })).toMatch(/Cannot reach the server/);
  });

  it('falls back for plain errors', () => {
    expect(getErrorMessage(new Error('boom'), 'Custom')).toBe('Custom');
    expect(getErrorMessage(null)).toMatch(/Something went wrong/);
  });
});
