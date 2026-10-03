import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, TouchableOpacity, View, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api, getErrorMessage } from '../lib/api';
import { getStoredUser } from '../lib/storage';
import {
  CONNECTOR_LABELS,
  CONNECTOR_SETTINGS_TEMPLATES,
  SETTINGS_CONNECTOR_TYPES,
  stripMaskedFields,
} from '../lib/connector';
import { Banner, Button, ChoiceChips } from '../components/ui';
import ConnectorFields from '../components/ConnectorFields';
import { colors } from '../theme';
import { styles } from './ConnectorSettingsScreen.styles';

const CONNECTOR_OPTIONS = SETTINGS_CONNECTOR_TYPES.map((value) => ({ value, label: CONNECTOR_LABELS[value] }));

const DEFAULT_CONFIGS = {
  postgresql: { host: 'db.example.com', port: 5432, database: 'client_db', user: 'lia_user', password: '' },
  mysql: { host: 'db.example.com', port: 3306, database: 'client_db', user: 'lia_user', password: '' },
  hubspot: { api_key: '' },
  salesforce: { instance_url: 'https://your-instance.salesforce.com', client_id: '', client_secret: '', username: '', password: '' },
  dynamics: { tenant_id: '', client_id: '', client_secret: '', dynamics_url: 'https://yourorg.crm.dynamics.com' },
};

export default function ConnectorSettingsScreen({ navigation }) {
  const [user, setUser] = useState(null);
  const [userLoaded, setUserLoaded] = useState(false);
  const [connectorType, setConnectorType] = useState('postgresql');
  const [config, setConfig] = useState({ ...DEFAULT_CONFIGS.postgresql });
  const [loadingCurrent, setLoadingCurrent] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getStoredUser().then((stored) => {
      if (cancelled) return;
      setUser(stored);
      setUserLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Show the saved connector (secrets arrive masked) instead of placeholder values.
  useEffect(() => {
    if (!userLoaded) return undefined;
    if (!user?.org_id) {
      setLoadingCurrent(false);
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get(`/organizations/${user.org_id}`);
        const org = res.data?.organization;
        const hasConfig = org?.connector_config && Object.keys(org.connector_config).length > 0;
        if (!cancelled && org && SETTINGS_CONNECTOR_TYPES.includes(org.connector_type) && hasConfig) {
          setConnectorType(org.connector_type);
          setConfig({ ...org.connector_config });
        }
      } catch {
        // Not fatal: the admin can still start from the template.
      } finally {
        if (!cancelled) setLoadingCurrent(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user, userLoaded]);

  const handleConnectorTypeChange = (type) => {
    setConnectorType(type);
    setConfig({ ...DEFAULT_CONFIGS[type] });
    setError('');
    setSuccess(false);
  };

  const handleSave = async () => {
    if (saving) return;
    setError('');
    setSuccess(false);

    if (!user?.org_id) {
      setError('No organization associated with your account.');
      return;
    }

    setSaving(true);
    try {
      const res = await api.patch(`/organizations/${user.org_id}/connector`, {
        connector_type: connectorType,
        // Secrets still showing the mask were not changed by the user: never send them back.
        connector_config: stripMaskedFields(config),
      });
      if (res.status === 200) setSuccess(true);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to save connector settings.'));
    } finally {
      setSaving(false);
    }
  };

  const fields = CONNECTOR_SETTINGS_TEMPLATES[connectorType] || [];

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.backBtn}
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          accessibilityLabel="Back"
          accessibilityHint="Returns to the assistant"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Text style={styles.backBtnText}>{'←'} Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle} accessibilityRole="header">Connector Settings</Text>
      </View>

      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text style={styles.subtitle}>
            Configure how Lia connects to your CRM or database. Saved secrets are hidden; leave them unchanged to keep the stored value.
          </Text>

          {loadingCurrent && (
            <View style={styles.loadingRow} accessibilityLiveRegion="polite" accessibilityLabel="Loading current settings">
              <ActivityIndicator color={colors.primary} />
            </View>
          )}

          <ChoiceChips
            label="Connector type"
            options={CONNECTOR_OPTIONS}
            value={connectorType}
            onChange={handleConnectorTypeChange}
          />

          <ConnectorFields
            fields={fields}
            config={config}
            onChange={(next) => {
              setConfig(next);
              setSuccess(false);
            }}
            onSubmit={handleSave}
            editable={!saving}
          />

          <Banner kind="error" message={error} />
          <Banner kind="success" message={success ? 'Settings saved successfully.' : ''} />

          <Button
            label="Save settings"
            onPress={handleSave}
            loading={saving}
            loadingLabel="Saving"
            disabled={loadingCurrent}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
