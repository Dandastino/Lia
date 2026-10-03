import {
  MIN_PASSWORD_LENGTH,
  isValidEmail,
  validateConnectorConfig,
  validateEditUser,
  validateLogin,
  validateNewPassword,
  validateNewUser,
  validateOrganization,
} from '../validation';

describe('validation', () => {
  it('validates email format', () => {
    expect(isValidEmail('a@b.co')).toBe(true);
    expect(isValidEmail(' a@b.co ')).toBe(true);
    expect(isValidEmail('a@b')).toBe(false);
    expect(isValidEmail('a b@c.de')).toBe(false);
    expect(isValidEmail(undefined)).toBe(false);
  });

  it('validateLogin', () => {
    expect(validateLogin({ email: '', password: '' })).toEqual({
      email: 'Enter your email address.',
      password: 'Enter your password.',
    });
    expect(validateLogin({ email: 'nope', password: 'x' }).email).toMatch(/valid email/);
    expect(validateLogin({ email: 'a@b.co', password: 'x' })).toEqual({});
  });

  it('validateNewUser', () => {
    expect(validateNewUser({ email: '', password: '', org_id: '' })).toEqual({
      email: "Enter the user's email address.",
      password: 'Enter a password.',
      org_id: 'Select an organization.',
    });
    expect(validateNewUser({ email: 'bad', password: '123', org_id: 'o' })).toEqual({
      email: 'Enter a valid email address, e.g. name@company.com.',
      password: `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`,
    });
    expect(validateNewUser({ email: 'a@b.co', password: '123456', org_id: 'o' })).toEqual({});
  });

  it('validateEditUser', () => {
    expect(validateEditUser({ email: ' ' }).email).toMatch(/email address/);
    expect(validateEditUser({ email: 'x' }).email).toMatch(/valid email/);
    expect(validateEditUser({ email: 'a@b.co' })).toEqual({});
  });

  it('validateNewPassword', () => {
    expect(validateNewPassword('')).toMatch(/Enter a new password/);
    expect(validateNewPassword('12345')).toMatch(/at least 6/);
    expect(validateNewPassword('123456')).toBe('');
  });

  it('validateConnectorConfig honours required fields and allowMasked', () => {
    const fields = [
      { field: 'host', label: 'Host', required: true },
      { field: 'port', label: 'Port', required: false },
    ];
    expect(validateConnectorConfig(fields, { host: '  ' })).toEqual({ host: 'Host is required.' });
    expect(validateConnectorConfig(fields, undefined)).toEqual({ host: 'Host is required.' });
    expect(validateConnectorConfig(fields, { host: 'h' })).toEqual({});
    expect(validateConnectorConfig(fields, {}, { allowMasked: true })).toEqual({});
  });

  it('validateOrganization', () => {
    expect(validateOrganization({ name: '  ' })).toEqual({ name: 'Enter the organization name.' });
    expect(validateOrganization({ name: 'Acme' })).toEqual({});
  });
});
