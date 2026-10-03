import AsyncStorage from '@react-native-async-storage/async-storage';

export const TOKEN_KEY = 'token';
export const USER_KEY = 'user';

// Raw key/value access (kept for existing callers).
export const storage = {
  getItem: (key) => AsyncStorage.getItem(key),
  setItem: (key, value) => AsyncStorage.setItem(key, value),
  removeItem: (key) => AsyncStorage.removeItem(key),
};

// Storage can fail and stored JSON can be corrupted: neither may crash the app.
export async function getToken() {
  try {
    return await AsyncStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function getStoredUser() {
  try {
    const raw = await AsyncStorage.getItem(USER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export async function saveSession(token, user) {
  await AsyncStorage.setItem(TOKEN_KEY, token);
  await AsyncStorage.setItem(USER_KEY, JSON.stringify(user));
}

export async function clearSession() {
  try {
    await AsyncStorage.removeItem(TOKEN_KEY);
    await AsyncStorage.removeItem(USER_KEY);
  } catch {
    // Nothing more we can do; the in-memory session is dropped by the caller.
  }
}

export const isAdminRole = (user) => user?.role === 'admin' || user?.role === 'owner';

// Screen a signed-in user lands on.
export const homeRouteFor = (user) => (isAdminRole(user) ? 'Admin' : 'Voice');
