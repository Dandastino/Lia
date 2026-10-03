import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  clearSession,
  getStoredUser,
  getToken,
  homeRouteFor,
  isAdminRole,
  saveSession,
  storage,
} from '../storage';

describe('storage', () => {
  it('round-trips a session', async () => {
    await saveSession('tok', { id: '1', role: 'user' });
    expect(await getToken()).toBe('tok');
    expect(await getStoredUser()).toEqual({ id: '1', role: 'user' });
  });

  it('clears the session', async () => {
    await saveSession('tok', { id: '1' });
    await clearSession();
    expect(await getToken()).toBeNull();
    expect(await getStoredUser()).toBeNull();
  });

  it('returns null for missing, corrupted or non-object user data', async () => {
    expect(await getStoredUser()).toBeNull();
    await AsyncStorage.setItem('user', '{not json');
    expect(await getStoredUser()).toBeNull();
    await AsyncStorage.setItem('user', '[1,2]');
    expect(await getStoredUser()).toBeNull();
    await AsyncStorage.setItem('user', 'null');
    expect(await getStoredUser()).toBeNull();
  });

  it('never throws when the underlying storage fails', async () => {
    AsyncStorage.getItem.mockRejectedValueOnce(new Error('disk'));
    expect(await getToken()).toBeNull();
    AsyncStorage.getItem.mockRejectedValueOnce(new Error('disk'));
    expect(await getStoredUser()).toBeNull();
    AsyncStorage.removeItem.mockRejectedValueOnce(new Error('disk'));
    await expect(clearSession()).resolves.toBeUndefined();
  });

  it('exposes raw key/value helpers', async () => {
    await storage.setItem('k', 'v');
    expect(await storage.getItem('k')).toBe('v');
    await storage.removeItem('k');
    expect(await storage.getItem('k')).toBeNull();
  });

  it('routes admins and owners to Admin, everyone else to Voice', () => {
    expect(isAdminRole({ role: 'admin' })).toBe(true);
    expect(isAdminRole({ role: 'owner' })).toBe(true);
    expect(isAdminRole({ role: 'user' })).toBe(false);
    expect(isAdminRole(null)).toBe(false);
    expect(homeRouteFor({ role: 'owner' })).toBe('Admin');
    expect(homeRouteFor({ role: 'user' })).toBe('Voice');
  });
});
