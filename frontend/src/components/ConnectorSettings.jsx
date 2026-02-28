import { useState } from 'react';
import { api } from '../lib/api';
import './ConnectorSettings.css';

const CONNECTOR_OPTIONS = [
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'hubspot', label: 'HubSpot' },
  { value: 'salesforce', label: 'Salesforce' },
  { value: 'dynamics', label: 'Dynamics 365' },
];

const DEFAULT_CONFIGS = {
  postgresql: {
    host: 'db.example.com',
    port: 5432,
    database: 'client_db',
    user: 'lia_user',
    password: 'change_me',
  },
  mysql: {
    host: 'db.example.com',
    port: 3306,
    database: 'client_db',
    user: 'lia_user',
    password: 'change_me',
  },
  hubspot: {
    api_key: 'your_hubspot_api_key',
  },
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

export default function ConnectorSettings({ user, onBack }) {
  const [connectorType, setConnectorType] = useState('postgresql');
  const [configJson, setConfigJson] = useState(
    JSON.stringify(DEFAULT_CONFIGS.postgresql, null, 2),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess(false);

    let parsedConfig = {};
    try {
      parsedConfig = configJson ? JSON.parse(configJson) : {};
    } catch (err) {
      setError('Connector config must be valid JSON.');
      setSaving(false);
      return;
    }

    try {
      const res = await api.patch(
        `/organizations/${user.org_id}/connector`,
        {
          connector_type: connectorType,
          connector_config: parsedConfig,
        },
      );

      if (res.status === 200) {
        setSuccess(true);
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save connector settings.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="connector-settings">
      <header className="connector-header">
        <div>
          <h1>Connector Settings</h1>
          <p className="connector-subtitle">
            Configure how Lia connects to your CRM or database for this organization.
          </p>
        </div>
        <button type="button" className="back-btn" onClick={onBack}>
          ← Back to assistant
        </button>
      </header>

      <main className="connector-content">
        <form onSubmit={handleSave} className="connector-form">
          <div className="form-group">
            <label htmlFor="connectorType">Connector type</label>
            <select
              id="connectorType"
              value={connectorType}
              onChange={(e) => {
                const nextType = e.target.value;
                setConnectorType(nextType);
                setConfigJson(
                  JSON.stringify(DEFAULT_CONFIGS[nextType], null, 2),
                );
              }}
            >
              {CONNECTOR_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="configJson">Connector configuration (JSON)</label>
            <textarea
              id="configJson"
              value={configJson}
              onChange={(e) => setConfigJson(e.target.value)}
              rows={10}
              className="config-textarea"
            />
            <p className="helper-text">
              Configure connector credentials in JSON. Use the template above as a
              starting point.
            </p>
          </div>

          {error && <div className="error-message">{error}</div>}
          {success && <div className="success-message">Settings saved.</div>}

          <button type="submit" className="submit-btn" disabled={saving}>
            {saving ? 'Saving...' : 'Save settings'}
          </button>
        </form>
      </main>
    </div>
  );
}

