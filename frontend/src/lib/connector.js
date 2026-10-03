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

export const CONNECTOR_LABELS = {
  internal: 'Internal',
  salesforce: 'Salesforce',
  hubspot: 'HubSpot',
  dynamics: 'Dynamics 365',
  mysql: 'MySQL',
  postgresql: 'PostgreSQL',
};

export const CONNECTOR_TYPES = Object.keys(CONNECTOR_LABELS);
