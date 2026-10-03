import { describe, it, expect } from 'vitest';
import {
  isValidEmail,
  validateConnectorConfig,
  validateEditUser,
  validateLogin,
  validateNewPassword,
  validateNewUser,
  validateOrganization,
} from './validation';
import { MASK, stripMaskedFields } from './connector';

describe('validation', () => {
  it('validates emails', () => {
    expect(isValidEmail('a@b.co')).toBe(true);
    expect(isValidEmail('nope')).toBe(false);
    expect(isValidEmail(undefined)).toBe(false);
  });

  it('validates the login form', () => {
    expect(validateLogin({ email: '', password: '' })).toEqual({
      email: expect.any(String),
      password: expect.any(String),
    });
    expect(validateLogin({ email: 'bad', password: 'x' }).email).toMatch(/valid email/i);
    expect(validateLogin({ email: 'a@b.co', password: 'x' })).toEqual({});
  });

  it('validates a new user', () => {
    const errors = validateNewUser({ email: '', password: '123', org_id: '' });
    expect(Object.keys(errors).sort()).toEqual(['email', 'org_id', 'password']);
    expect(validateNewUser({ email: 'a@b.co', password: '123456', org_id: '1' })).toEqual({});
    expect(validateNewUser({ email: 'a@b.co', password: '', org_id: '1' }).password).toMatch(/enter a password/i);
    expect(validateNewUser({ email: 'bad', password: '123456', org_id: '1' }).email).toMatch(/valid email/i);
  });

  it('validates user edits, passwords, organizations', () => {
    expect(validateEditUser({ email: '' }).email).toBeTruthy();
    expect(validateEditUser({ email: 'x' }).email).toBeTruthy();
    expect(validateEditUser({ email: 'a@b.co' })).toEqual({});
    expect(validateNewPassword('')).toBeTruthy();
    expect(validateNewPassword('123')).toMatch(/at least 6/);
    expect(validateNewPassword('123456')).toBe('');
    expect(validateOrganization({ name: ' ' }).name).toBeTruthy();
    expect(validateOrganization({ name: 'Acme' })).toEqual({});
  });

  it('validates required connector fields', () => {
    const fields = [
      { field: 'host', label: 'Host', required: true },
      { field: 'port', label: 'Port', required: false },
    ];
    expect(validateConnectorConfig(fields, { host: ' ' })).toEqual({ host: 'Host is required.' });
    expect(validateConnectorConfig(fields, { host: 'h' })).toEqual({});
    expect(validateConnectorConfig(fields, undefined)).toEqual({ host: 'Host is required.' });
  });
});

describe('stripMaskedFields', () => {
  it('drops fields that still hold the mask', () => {
    expect(stripMaskedFields({ host: 'h', password: MASK, token: 't' })).toEqual({ host: 'h', token: 't' });
    expect(stripMaskedFields(undefined)).toEqual({});
  });
});
