import PropTypes from 'prop-types';
import { useState } from 'react';
import Modal from '../Modal';
import Field from './Field';
import { MIN_PASSWORD_LENGTH, validateNewPassword } from '../../lib/validation';

export default function ResetPasswordDialog({ user, busy, onSubmit, onCancel }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    const message = validateNewPassword(password);
    setError(message);
    if (message) {
      document.getElementById('new-password')?.focus();
      return;
    }
    onSubmit(password);
  };

  return (
    <Modal labelledBy="reset-title" onClose={busy ? undefined : onCancel}>
      <h2 id="reset-title">Reset password for {user.email}</h2>
      <form onSubmit={handleSubmit} noValidate aria-busy={busy} className="form">
        <Field
          id="new-password"
          label="New password"
          required
          error={error}
          type="password"
          autoComplete="new-password"
          placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          data-autofocus
        />
        <div className="form-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Resetting...' : 'Reset password'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}

ResetPasswordDialog.propTypes = { user: PropTypes.shape({ email: PropTypes.string }).isRequired, busy: PropTypes.bool, onSubmit: PropTypes.func.isRequired, onCancel: PropTypes.func.isRequired };
