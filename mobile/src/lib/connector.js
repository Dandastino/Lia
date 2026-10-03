// Connector helpers (mirrors frontend/src/lib/connector.js).

// The backend replaces secret values in connector_config responses with this
// placeholder. It must never be sent back as if it were a real new value.
export const MASK = '********';

// Return a copy of config without fields that still hold the mask.
export function stripMaskedFields(config) {
  const out = {};
  for (const [key, value] of Object.entries(config || {})) {
    if (value !== MASK) out[key] = value;
  }
  return out;
}

// True when at least one field holds a non-empty value.
export function hasConfigValues(config) {
  return Object.values(config || {}).some((v) => String(v ?? '').trim() !== '');
}

// Form fields used when an admin creates / edits an organization.
export const CONNECTOR_CONFIG_TEMPLATES = {
  postgresql: [
    { field: 'host', label: 'Host', type: 'text', placeholder: 'db.example.com', required: true },
    { field: 'port', label: 'Port', type: 'number', placeholder: '5432', required: false },
    { field: 'database', label: 'Database', type: 'text', placeholder: 'my_database', required: true },
    { field: 'user', label: 'Username', type: 'text', placeholder: 'postgres', required: true },
    { field: 'password', label: 'Password', type: 'password', placeholder: '', required: true },
  ],
  mysql: [
    { field: 'host', label: 'Host', type: 'text', placeholder: 'db.example.com', required: true },
    { field: 'port', label: 'Port', type: 'number', placeholder: '3306', required: false },
    { field: 'database', label: 'Database', type: 'text', placeholder: 'my_database', required: true },
    { field: 'user', label: 'Username', type: 'text', placeholder: 'root', required: true },
    { field: 'password', label: 'Password', type: 'password', placeholder: '', required: true },
  ],
  salesforce: [
    { field: 'client_id', label: 'Client ID', type: 'text', placeholder: 'Your Salesforce Client ID', required: true },
    { field: 'client_secret', label: 'Client Secret', type: 'password', placeholder: '', required: true },
    { field: 'username', label: 'Username', type: 'text', placeholder: 'user@example.com', required: true },
    { field: 'password', label: 'Password', type: 'password', placeholder: '', required: true },
  ],
  hubspot: [
    { field: 'api_key', label: 'API Key', type: 'password', placeholder: 'Your HubSpot API Key', required: true },
  ],
  dynamics: [
    { field: 'tenant_id', label: 'Tenant ID', type: 'text', placeholder: 'Your Azure Tenant ID', required: true },
    { field: 'client_id', label: 'Client ID', type: 'text', placeholder: 'Your Client ID', required: true },
    { field: 'client_secret', label: 'Client Secret', type: 'password', placeholder: '', required: true },
  ],
};

// Fields of the self-service "Connector Settings" screen (a few more than the
// admin form, e.g. instance/Dynamics URLs). Nothing is required here: the
// screen starts from the stored (masked) configuration.
export const CONNECTOR_SETTINGS_TEMPLATES = {
  postgresql: CONNECTOR_CONFIG_TEMPLATES.postgresql.map((f) => ({ ...f, required: false })),
  mysql: CONNECTOR_CONFIG_TEMPLATES.mysql.map((f) => ({ ...f, required: false })),
  hubspot: CONNECTOR_CONFIG_TEMPLATES.hubspot.map((f) => ({ ...f, required: false })),
  salesforce: [
    { field: 'instance_url', label: 'Instance URL', type: 'url', placeholder: 'https://your-instance.salesforce.com' },
    { field: 'client_id', label: 'Client ID', type: 'text', placeholder: 'Your Client ID' },
    { field: 'client_secret', label: 'Client Secret', type: 'password', placeholder: '' },
    { field: 'username', label: 'Username', type: 'text', placeholder: 'user@example.com' },
    { field: 'password', label: 'Password + Token', type: 'password', placeholder: '' },
  ],
  dynamics: [
    { field: 'tenant_id', label: 'Tenant ID', type: 'text', placeholder: 'Your Azure Tenant ID' },
    { field: 'client_id', label: 'Client ID', type: 'text', placeholder: 'Your Client ID' },
    { field: 'client_secret', label: 'Client Secret', type: 'password', placeholder: '' },
    { field: 'dynamics_url', label: 'Dynamics URL', type: 'url', placeholder: 'https://yourorg.crm.dynamics.com' },
  ],
};

export const CONNECTOR_LABELS = {
  internal: 'Internal',
  salesforce: 'Salesforce',
  hubspot: 'HubSpot',
  dynamics: 'Dynamics 365',
  mysql: 'MySQL',
  postgresql: 'PostgreSQL',
};

export const CONNECTOR_TYPES = Object.keys(CONNECTOR_LABELS);

// Connectors selectable on the Connector Settings screen (no "internal").
export const SETTINGS_CONNECTOR_TYPES = ['postgresql', 'mysql', 'hubspot', 'salesforce', 'dynamics'];

// Map a template field to TextInput props.
export function inputPropsFor(field) {
  const secure = field.type === 'password';
  return {
    secureTextEntry: secure,
    keyboardType: field.type === 'number' ? 'numeric' : field.type === 'url' ? 'url' : 'default',
    autoCapitalize: 'none',
    autoCorrect: false,
    // Credentials for a third-party system must not be offered to the OS password manager.
    autoComplete: 'off',
    textContentType: 'none',
  };
}
