import PropTypes from 'prop-types';
import { useState } from 'react';
import Field from './Field';
import { MIN_PASSWORD_LENGTH, validateEditUser, validateNewUser } from '../../lib/validation';

const ROLE_OPTIONS = (
  <>
    <option value="user">User</option>
    <option value="admin">Admin</option>
    <option value="owner">Owner</option>
  </>
);

/** Create / edit user form. `mode` is 'create' or 'edit'. */
export default function UserForm({ mode, initial, organizations, busy, onSubmit, onCancel }) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const isCreate = mode === 'create';
  const prefix = isCreate ? 'user' : 'edit_user';

  const handleSubmit = (e) => {
    e.preventDefault();
    const nextErrors = isCreate ? validateNewUser(form) : validateEditUser(form);
    setErrors(nextErrors);
    const first = Object.keys(nextErrors)[0];
    if (first) {
      document.getElementById(`${prefix}_${first === 'org_id' ? 'org' : first}`)?.focus();
      return;
    }
    onSubmit(form);
  };

  const update = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  return (
    <form onSubmit={handleSubmit} className="form" noValidate aria-busy={busy}>
      <Field
        id={`${prefix}_email`}
        label="Email"
        required
        error={errors.email}
        type="email"
        autoComplete="off"
        placeholder="user@example.com"
        value={form.email}
        onChange={update('email')}
      />

      {isCreate && (
        <Field
          id="user_password"
          label="Password"
          required
          error={errors.password}
          type="password"
          autoComplete="new-password"
          value={form.password}
          onChange={update('password')}
          aria-describedby={errors.password ? 'user_password-error' : 'user_password-hint'}
        />
      )}
      {isCreate && !errors.password && (
        <p id="user_password-hint" className="helper-text" style={{ marginTop: '-1rem' }}>
          At least {MIN_PASSWORD_LENGTH} characters.
        </p>
      )}

      <Field
        id={`${prefix}_org`}
        label="Organization"
        required={isCreate}
        error={errors.org_id}
        as="select"
        value={form.org_id}
        onChange={update('org_id')}
      >
        <option value="">{isCreate ? 'Select an organization' : 'Unassigned'}</option>
        {organizations.map((org) => (
          <option key={org.id} value={org.id}>{org.name}</option>
        ))}
      </Field>

      <Field id={`${prefix}_role`} label="Role" required as="select" value={form.role} onChange={update('role')}>
        {ROLE_OPTIONS}
      </Field>

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {isCreate ? (busy ? 'Creating...' : 'Create user') : busy ? 'Saving...' : 'Save user'}
        </button>
        {onCancel && (
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

UserForm.propTypes = { mode: PropTypes.oneOf(['create', 'edit']).isRequired, initial: PropTypes.shape({ email: PropTypes.string, password: PropTypes.string, org_id: PropTypes.string, role: PropTypes.string }).isRequired, organizations: PropTypes.arrayOf(PropTypes.shape({ id: PropTypes.string, name: PropTypes.string, industry: PropTypes.string, connector_type: PropTypes.string, user_count: PropTypes.number })).isRequired, busy: PropTypes.bool, onSubmit: PropTypes.func.isRequired, onCancel: PropTypes.func };
