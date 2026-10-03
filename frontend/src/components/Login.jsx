import PropTypes from 'prop-types';
import { useState } from 'react';
import { api, getErrorMessage } from '../lib/api';
import { saveSession } from '../lib/storage';
import { validateLogin } from '../lib/validation';

export default function Login({ onLoginSuccess }) {
  const [formData, setFormData] = useState({ email: '', password: '' });
  const [fieldErrors, setFieldErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (fieldErrors[name]) setFieldErrors((prev) => ({ ...prev, [name]: undefined }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    const errors = validateLogin(formData);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      // Move focus to the first invalid field so keyboard/screen-reader users land on it.
      document.getElementById(errors.email ? 'email' : 'password')?.focus();
      return;
    }

    setLoading(true);
    try {
      const response = await api.post('/login', {
        email: formData.email.trim(),
        password: formData.password,
      });

      if (response.data.access_token && response.data.user) {
        saveSession(response.data.access_token, response.data.user);
        onLoginSuccess(response.data.user);
      } else {
        setError('The server sent an unexpected response. Please try again.');
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Sign-in failed. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-page">
      <div className="card card-narrow">
        <h1 className="brand">Lia Assistant</h1>
        <p className="card-subtitle">Sign in to continue</p>

        <div role="alert" className="alert-slot">
          {error && <div className="alert alert-error">{error}</div>}
        </div>

        <form onSubmit={handleSubmit} noValidate aria-busy={loading} className="form">
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              type="email"
              id="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              autoComplete="username"
              placeholder="name@company.com"
              aria-required="true"
              aria-invalid={fieldErrors.email ? 'true' : undefined}
              aria-describedby={fieldErrors.email ? 'email-error' : undefined}
            />
            {fieldErrors.email && <p id="email-error" className="field-error">{fieldErrors.email}</p>}
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              type="password"
              id="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              autoComplete="current-password"
              aria-required="true"
              aria-invalid={fieldErrors.password ? 'true' : undefined}
              aria-describedby={fieldErrors.password ? 'password-error' : undefined}
            />
            {fieldErrors.password && <p id="password-error" className="field-error">{fieldErrors.password}</p>}
          </div>

          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    </main>
  );
}

Login.propTypes = { onLoginSuccess: PropTypes.func.isRequired };
