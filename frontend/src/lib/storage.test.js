import { describe, it, expect, vi, beforeEach } from 'vitest';
import { clearSession, getStoredUser, getToken, isAdminRole, saveSession } from './storage';

describe('storage helpers', () => {
  beforeEach(() => localStorage.clear());

  it('round-trips a session', () => {
    saveSession('tok', { email: 'a@b.co', role: 'user' });
    expect(getToken()).toBe('tok');
    expect(getStoredUser()).toEqual({ email: 'a@b.co', role: 'user' });
    clearSession();
    expect(getToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });

  it('returns null for corrupted or non-object JSON instead of throwing', () => {
    localStorage.setItem('user', '{not json');
    expect(getStoredUser()).toBeNull();
    localStorage.setItem('user', '"text"');
    expect(getStoredUser()).toBeNull();
    localStorage.setItem('user', '[1]');
    expect(getStoredUser()).toBeNull();
  });

  it('survives unavailable storage', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(getToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
    spy.mockRestore();

    const setSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const removeSpy = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => saveSession('t', {})).not.toThrow();
    expect(() => clearSession()).not.toThrow();
    setSpy.mockRestore();
    removeSpy.mockRestore();
  });

  it('identifies admin roles', () => {
    expect(isAdminRole({ role: 'admin' })).toBe(true);
    expect(isAdminRole({ role: 'owner' })).toBe(true);
    expect(isAdminRole({ role: 'user' })).toBe(false);
    expect(isAdminRole(null)).toBe(false);
  });
});
