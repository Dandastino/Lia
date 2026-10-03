import { useState } from 'react';
import { Button, ChoiceChips, Field } from '../../components/ui';
import ConnectorFields from '../../components/ConnectorFields';
import { CONNECTOR_CONFIG_TEMPLATES, CONNECTOR_LABELS, CONNECTOR_TYPES } from '../../lib/connector';
import { validateConnectorConfig, validateOrganization } from '../../lib/validation';

const TYPE_OPTIONS = CONNECTOR_TYPES.map((value) => ({ value, label: CONNECTOR_LABELS[value] }));

/**
 * Create / edit organization form (mode is 'create' or 'edit').
 * In edit mode the stored secrets are never shown, so connector fields are only
 * required when the connector type changes (same rule as the web admin).
 */
export default function OrganizationForm({ mode, initial, busy, onSubmit, onCancel }) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const [configErrors, setConfigErrors] = useState({});
  const typeChanged = mode === 'create' || form.connector_type !== initial.connector_type;
  const fields = CONNECTOR_CONFIG_TEMPLATES[form.connector_type] || [];

  const handleSubmit = () => {
    if (busy) return;
    const nextErrors = validateOrganization(form);
    const nextConfigErrors =
      form.connector_type !== 'internal' && typeChanged
        ? validateConnectorConfig(fields, form.connector_config)
        : {};
    setErrors(nextErrors);
    setConfigErrors(nextConfigErrors);
    if (Object.keys(nextErrors).length || Object.keys(nextConfigErrors).length) return;
    onSubmit(form);
  };

  return (
    <>
      <Field
        label="Organization name"
        required
        error={errors.name}
        value={form.name}
        onChangeText={(name) => setForm((p) => ({ ...p, name }))}
        placeholder="e.g. Acme Corporation"
        returnKeyType="next"
        editable={!busy}
      />
      <Field
        label="Industry"
        value={form.industry}
        onChangeText={(industry) => setForm((p) => ({ ...p, industry }))}
        placeholder="e.g. Technology, Finance"
        returnKeyType="next"
        editable={!busy}
      />
      <ChoiceChips
        label="Connector type"
        options={TYPE_OPTIONS}
        value={form.connector_type}
        onChange={(connector_type) => {
          setForm((p) => ({ ...p, connector_type, connector_config: {} }));
          setConfigErrors({});
        }}
      />
      {form.connector_type !== 'internal' && (
        <ConnectorFields
          fields={fields}
          config={form.connector_config}
          onChange={(connector_config) => setForm((p) => ({ ...p, connector_config }))}
          errors={configErrors}
          onSubmit={handleSubmit}
          editable={!busy}
          hint={
            mode === 'edit' && !typeChanged
              ? 'Stored credentials are hidden. Leave these fields empty to keep the current configuration.'
              : undefined
          }
        />
      )}
      <Button
        label={mode === 'edit' ? 'Save organization' : 'Create organization'}
        onPress={handleSubmit}
        loading={busy}
        loadingLabel={mode === 'edit' ? 'Saving' : 'Creating'}
      />
      {onCancel && <Button label="Cancel" variant="secondary" onPress={onCancel} disabled={busy} style={{ marginTop: 12 }} />}
    </>
  );
}
