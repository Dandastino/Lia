import PropTypes from 'prop-types';
import { useState } from 'react';
import Field from './Field';
import ConnectorConfigForm from './ConnectorConfigForm';
import { CONNECTOR_CONFIG_TEMPLATES, CONNECTOR_LABELS, CONNECTOR_TYPES } from '../../lib/connector';
import { validateConnectorConfig, validateOrganization } from '../../lib/validation';

/**
 * Create / edit organization form. `mode` is 'create' or 'edit'.
 * In edit mode the stored secrets are never shown, so connector fields are only
 * required when the connector type changes.
 */
export default function OrganizationForm({ mode, initial, busy, onSubmit, onCancel }) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const [configErrors, setConfigErrors] = useState({});
  const prefix = mode === 'edit' ? 'edit_org' : 'org';
  const typeChanged = mode === 'create' || form.connector_type !== initial.connector_type;

  const handleSubmit = (e) => {
    e.preventDefault();
    const nextErrors = validateOrganization(form);
    const nextConfigErrors =
      form.connector_type !== 'internal' && typeChanged
        ? validateConnectorConfig(CONNECTOR_CONFIG_TEMPLATES[form.connector_type] || [], form.connector_config)
        : {};
    setErrors(nextErrors);
    setConfigErrors(nextConfigErrors);

    const firstInvalid = nextErrors.name ? `${prefix}_name` : Object.keys(nextConfigErrors)[0] && `cfg_${prefix}_${Object.keys(nextConfigErrors)[0]}`;
    if (firstInvalid) {
      document.getElementById(firstInvalid)?.focus();
      return;
    }
    onSubmit(form);
  };

  const submitLabel = mode === 'edit' ? 'Save organization' : 'Create organization';
  const busyLabel = mode === 'edit' ? 'Saving...' : 'Creating...';

  return (
    <form onSubmit={handleSubmit} className="form" noValidate aria-busy={busy}>
      <Field
        id={`${prefix}_name`}
        label="Organization name"
        required
        error={errors.name}
        type="text"
        placeholder="e.g., Acme Corporation"
        value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })}
      />

      <Field
        id={`${prefix}_industry`}
        label="Industry"
        type="text"
        placeholder="e.g., Technology, Finance"
        value={form.industry}
        onChange={(e) => setForm({ ...form, industry: e.target.value })}
      />

      <Field
        id={`${prefix}_connector`}
        label="Connector type"
        required
        as="select"
        value={form.connector_type}
        onChange={(e) => {
          setForm({ ...form, connector_type: e.target.value, connector_config: {} });
          setConfigErrors({});
        }}
      >
        {CONNECTOR_TYPES.map((type) => (
          <option key={type} value={type}>{CONNECTOR_LABELS[type]}</option>
        ))}
      </Field>

      <ConnectorConfigForm
        connectorType={form.connector_type}
        config={form.connector_config}
        onChange={(config) => setForm({ ...form, connector_config: config })}
        errors={configErrors}
        idPrefix={`cfg_${prefix}`}
        hint={
          mode === 'edit' && !typeChanged
            ? 'Stored credentials are hidden. Leave these fields empty to keep the current configuration.'
            : undefined
        }
      />

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? busyLabel : submitLabel}
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

OrganizationForm.propTypes = { mode: PropTypes.oneOf(['create', 'edit']).isRequired, initial: PropTypes.shape({ name: PropTypes.string, industry: PropTypes.string, connector_type: PropTypes.string, connector_config: PropTypes.object }).isRequired, busy: PropTypes.bool, onSubmit: PropTypes.func.isRequired, onCancel: PropTypes.func };
