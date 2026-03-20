import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '../lib/api';
import { styles } from './ConnectorSettingsScreen.styles';
import { storage } from '../lib/storage';

const CONNECTOR_OPTIONS = [
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'hubspot', label: 'HubSpot' },
  { value: 'salesforce', label: 'Salesforce' },
  { value: 'dynamics', label: 'Dynamics 365' },
];

const DEFAULT_CONFIGS = {
  postgresql: { host: 'db.example.com', port: 5432, database: 'client_db', user: 'lia_user', password: '' },
  mysql: { host: 'db.example.com', port: 3306, database: 'client_db', user: 'lia_user', password: '' },
  hubspot: { api_key: '' },
  salesforce: { instance_url: 'https://your-instance.salesforce.com', client_id: '', client_secret: '', username: '', password: '' },
  dynamics: { tenant_id: '', client_id: '', client_secret: '', dynamics_url: 'https://yourorg.crm.dynamics.com' },
};

const CONNECTOR_FIELDS = {
  postgresql: [
    { field: 'host', label: 'Host', placeholder: 'db.example.com' },
    { field: 'port', label: 'Port', placeholder: '5432', keyboardType: 'numeric' },
    { field: 'database', label: 'Database', placeholder: 'client_db' },
    { field: 'user', label: 'Username', placeholder: 'lia_user' },
    { field: 'password', label: 'Password', placeholder: '••••••••', secure: true },
  ],
  mysql: [
    { field: 'host', label: 'Host', placeholder: 'db.example.com' },
    { field: 'port', label: 'Port', placeholder: '3306', keyboardType: 'numeric' },
    { field: 'database', label: 'Database', placeholder: 'client_db' },
    { field: 'user', label: 'Username', placeholder: 'lia_user' },
    { field: 'password', label: 'Password', placeholder: '••••••••', secure: true },
  ],
  hubspot: [
    { field: 'api_key', label: 'API Key', placeholder: 'Your HubSpot API Key', secure: true },
  ],
  salesforce: [
    { field: 'instance_url', label: 'Instance URL', placeholder: 'https://your-instance.salesforce.com' },
    { field: 'client_id', label: 'Client ID', placeholder: 'Your Client ID' },
    { field: 'client_secret', label: 'Client Secret', placeholder: '••••••••', secure: true },
    { field: 'username', label: 'Username', placeholder: 'user@example.com' },
    { field: 'password', label: 'Password + Token', placeholder: '••••••••', secure: true },
  ],
  dynamics: [
    { field: 'tenant_id', label: 'Tenant ID', placeholder: 'Your Azure Tenant ID' },
    { field: 'client_id', label: 'Client ID', placeholder: 'Your Client ID' },
    { field: 'client_secret', label: 'Client Secret', placeholder: '••••••••', secure: true },
    { field: 'dynamics_url', label: 'Dynamics URL', placeholder: 'https://yourorg.crm.dynamics.com' },
  ],
};

export default function ConnectorSettingsScreen({ navigation }) {
  const [user, setUser] = useState(null);
  const [connectorType, setConnectorType] = useState('postgresql');
  const [config, setConfig] = useState({ ...DEFAULT_CONFIGS.postgresql });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    storage.getItem('user').then((str) => {
      if (str) setUser(JSON.parse(str));
    });
  }, []);

  const handleConnectorTypeChange = (type) => {
    setConnectorType(type);
    setConfig({ ...DEFAULT_CONFIGS[type] });
    setError('');
    setSuccess(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    setSuccess(false);

    if (!user?.org_id) {
      setError('No organization associated with your account.');
      setSaving(false);
      return;
    }

    try {
      const res = await api.patch(`/organizations/${user.org_id}/connector`, {
        connector_type: connectorType,
        connector_config: config,
      });
      if (res.status === 200) {
        setSuccess(true);
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save connector settings.');
    } finally {
      setSaving(false);
    }
  };

  const fields = CONNECTOR_FIELDS[connectorType] || [];

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.backBtnText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Connector Settings</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.subtitle}>
          Configure how Lia connects to your CRM or database.
        </Text>

        {/* Connector type selector */}
        <Text style={styles.label}>Connector Type</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
          {CONNECTOR_OPTIONS.map((opt) => (
            <TouchableOpacity
              key={opt.value}
              style={[styles.chip, connectorType === opt.value && styles.chipActive]}
              onPress={() => handleConnectorTypeChange(opt.value)}
            >
              <Text style={[styles.chipText, connectorType === opt.value && styles.chipTextActive]}>
                {opt.label}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Dynamic config fields */}
        <View style={styles.fieldsContainer}>
          {fields.map((f) => (
            <View key={f.field} style={styles.formGroup}>
              <Text style={styles.label}>{f.label}</Text>
              <TextInput
                style={styles.input}
                value={String(config[f.field] ?? '')}
                onChangeText={(v) => setConfig((prev) => ({ ...prev, [f.field]: v }))}
                placeholder={f.placeholder}
                placeholderTextColor="#555"
                secureTextEntry={!!f.secure}
                keyboardType={f.keyboardType || 'default'}
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
          ))}
        </View>

        {!!error && (
          <View style={styles.errorContainer}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {success && (
          <View style={styles.successContainer}>
            <Text style={styles.successText}>✓ Settings saved successfully.</Text>
          </View>
        )}

        <TouchableOpacity style={[styles.submitBtn, saving && styles.submitBtnDisabled]} onPress={handleSave} disabled={saving}>
          {saving ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.submitBtnText}>Save Settings</Text>
          )}
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}
