import PropTypes from 'prop-types';
import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../lib/api';
import { MASK, stripMaskedFields } from '../lib/connector';

const CONNECTOR_OPTIONS = [
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'hubspot', label: 'HubSpot' },
  { value: 'salesforce', label: 'Salesforce' },
  { value: 'dynamics', label: 'Dynamics 365' },
];

const DEFAULT_CONFIGS = {
  postgresql: { host: 'db.example.com', port: 5432, database: 'client_db', user: 'lia_user', password: 'change_me' },
  mysql: { host: 'db.example.com', port: 3306, database: 'client_db', user: 'lia_user', password: 'change_me' },
  hubspot: { api_key: 'your_hubspot_api_key' },
  salesforce: {
    instance_url: 'https://your-instance.salesforce.com',
    client_id: 'your_client_id',
    client_secret: 'your_client_secret',
    username: 'user@example.com',
    password: 'password+token',
  },
  dynamics: {
    tenant_id: 'your_tenant_id',
    client_id: 'your_client_id',
    client_secret: 'your_client_secret',
    dynamics_url: 'https://yourorg.crm.dynamics.com',
  },
};

const pretty = (value) => JSON.stringify(value, null, 2);

export default function ConnectorSettings({ user, onBack }) {
  const [connectorType, setConnectorType] = useState('postgresql');
  const [configJson, setConfigJson] = useState(pretty(DEFAULT_CONFIGS.postgresql));
  const [loadingCurrent, setLoadingCurrent] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [jsonError, setJsonError] = useState('');
  const [success, setSuccess] = useState(false);

  // Show the saved connector (secrets arrive masked) instead of placeholder values.
  useEffect(() => {
    let cancelled = false;
    async function loadCurrent() {
      try {
        const res = await api.get(`/organizations/${user.org_id}`);
        const org = res.data?.organization;
        const hasConfig = org?.connector_config && Object.keys(org.connector_config).length > 0;
        if (!cancelled && org && CONNECTOR_OPTIONS.some((o) => o.value === org.connector_type) && hasConfig) {
          setConnectorType(org.connector_type);
          setConfigJson(pretty(org.connector_config));
        }
      } catch {
        // Not fatal: the admin can still start from the template.
      } finally {
        if (!cancelled) setLoadingCurrent(false);
      }
    }
    loadCurrent();
    return () => {
      cancelled = true;
    };
  }, [user.org_id]);

  const handleSave = async (e) => {
    e.preventDefault();
    setError('');
    setJsonError('');
    setSuccess(false);

    let parsedConfig = {};
    try {
      parsedConfig = configJson.trim() ? JSON.parse(configJson) : {};
      if (parsedConfig === null || typeof parsedConfig !== 'object' || Array.isArray(parsedConfig)) {
        throw new Error('not an object');
      }
    } catch {
      setJsonError('The configuration must be a valid JSON object, e.g. {"host": "db.example.com"}.');
      document.getElementById('configJson')?.focus();
      return;
    }

    setSaving(true);
    try {
      const res = await api.patch(`/organizations/${user.org_id}/connector`, {
        connector_type: connectorType,
        // Secrets still showing the mask were not changed by the user: do not send them.
        connector_config: stripMaskedFields(parsedConfig),
      });
      if (res.status === 200) setSuccess(true);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to save connector settings.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page on-gradient">
      <header className="app-header">
        <div>
          <h1>Connector settings</h1>
          <p>Configure how Lia connects to your CRM or database for this organization.</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={onBack}>
          <span aria-hidden="true">&larr;</span> Back to assistant
        </button>
      </header>

      <main className="page-main" id="main">
        <form onSubmit={handleSave} className="panel form" noValidate aria-busy={saving || loadingCurrent}>
          <div className="form-group">
            <label htmlFor="connectorType">Connector type</label>
            <select
              id="connectorType"
              value={connectorType}
              onChange={(e) => {
                const nextType = e.target.value;
                setConnectorType(nextType);
                setConfigJson(pretty(DEFAULT_CONFIGS[nextType]));
                setJsonError('');
                setSuccess(false);
              }}
            >
              {CONNECTOR_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="configJson">Connector configuration (JSON)</label>
            <textarea
              id="configJson"
              value={configJson}
              onChange={(e) => {
                setConfigJson(e.target.value);
                setSuccess(false);
              }}
              rows={10}
              className="config-textarea"
              spellCheck={false}
              disabled={loadingCurrent}
              aria-invalid={jsonError ? 'true' : undefined}
              aria-describedby={jsonError ? 'configJson-help configJson-error' : 'configJson-help'}
            />
            <p id="configJson-help" className="helper-text">
              Start from the template and replace the sample values. Secrets saved earlier appear as{' '}
              <code>{MASK}</code>; leave them as they are to keep the stored value.
            </p>
            {jsonError && <p id="configJson-error" className="field-error">{jsonError}</p>}
          </div>

          <div role="alert">{error && <div className="alert alert-error">{error}</div>}</div>
          <div role="status">{success && <div className="alert alert-success">Settings saved.</div>}</div>

          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={saving || loadingCurrent}>
              {saving ? 'Saving...' : 'Save settings'}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}

ConnectorSettings.propTypes = { user: PropTypes.shape({ org_id: PropTypes.string }).isRequired, onBack: PropTypes.func.isRequired };
