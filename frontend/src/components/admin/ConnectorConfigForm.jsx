import PropTypes from 'prop-types';
import { CONNECTOR_CONFIG_TEMPLATES, CONNECTOR_LABELS } from '../../lib/connector';

export default function ConnectorConfigForm({ connectorType, config, onChange, errors = {}, idPrefix = 'cfg', hint }) {
  if (connectorType === 'internal') {
    return <p className="text-secondary">No configuration needed for the internal connector.</p>;
  }

  const fields = CONNECTOR_CONFIG_TEMPLATES[connectorType] || [];

  return (
    <fieldset className="connector-config-group">
      <legend className="visually-hidden">{CONNECTOR_LABELS[connectorType]} configuration</legend>
      <h3 aria-hidden="true">{CONNECTOR_LABELS[connectorType]} configuration</h3>
      {hint && <p className="helper-text">{hint}</p>}
      {fields.map((field) => {
        const id = `${idPrefix}_${field.field}`;
        const err = errors[field.field];
        return (
          <div key={field.field} className="form-group">
            <label htmlFor={id} className={field.required ? 'is-required' : undefined}>
              {field.label}
            </label>
            <input
              type={field.type}
              id={id}
              placeholder={field.placeholder}
              value={config[field.field] ?? ''}
              onChange={(e) => onChange({ ...config, [field.field]: e.target.value })}
              autoComplete={field.type === 'password' ? 'new-password' : 'off'}
              aria-required={field.required ? 'true' : undefined}
              aria-invalid={err ? 'true' : undefined}
              aria-describedby={err ? `${id}-error` : undefined}
            />
            {err && <p id={`${id}-error`} className="field-error">{err}</p>}
          </div>
        );
      })}
    </fieldset>
  );
}

ConnectorConfigForm.propTypes = { connectorType: PropTypes.string.isRequired, config: PropTypes.object.isRequired, onChange: PropTypes.func.isRequired, errors: PropTypes.object, idPrefix: PropTypes.string, hint: PropTypes.string };
