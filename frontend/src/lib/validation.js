// Small, dependency-free form validators. They return an object of
// {fieldName: "message"}; an empty object means the form is valid.

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const MIN_PASSWORD_LENGTH = 6; // same minimum the reset-password form already advertised

export const isValidEmail = (value) => EMAIL_PATTERN.test((value || '').trim());

export function validateLogin({ email, password }) {
  const errors = {};
  if (!email.trim()) errors.email = 'Enter your email address.';
  else if (!isValidEmail(email)) errors.email = 'Enter a valid email address, e.g. name@company.com.';
  if (!password) errors.password = 'Enter your password.';
  return errors;
}

export function validateNewUser({ email, password, org_id }) {
  const errors = {};
  if (!email.trim()) errors.email = 'Enter the user\'s email address.';
  else if (!isValidEmail(email)) errors.email = 'Enter a valid email address, e.g. name@company.com.';
  if (!password) errors.password = 'Enter a password.';
  else if (password.length < MIN_PASSWORD_LENGTH) {
    errors.password = `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (!org_id) errors.org_id = 'Select an organization.';
  return errors;
}

export function validateEditUser({ email }) {
  const errors = {};
  if (!email.trim()) errors.email = 'Enter the user\'s email address.';
  else if (!isValidEmail(email)) errors.email = 'Enter a valid email address, e.g. name@company.com.';
  return errors;
}

export function validateNewPassword(password) {
  if (!password) return 'Enter a new password.';
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  return '';
}

// connector_config fields required by the form: {field, label, required}[]
export function validateConnectorConfig(fields, config, { allowMasked = false } = {}) {
  const errors = {};
  for (const f of fields) {
    const value = (config?.[f.field] ?? '').toString().trim();
    if (f.required && !value && !allowMasked) errors[f.field] = `${f.label} is required.`;
  }
  return errors;
}

export function validateOrganization({ name }) {
  const errors = {};
  if (!name.trim()) errors.name = 'Enter the organization name.';
  return errors;
}
