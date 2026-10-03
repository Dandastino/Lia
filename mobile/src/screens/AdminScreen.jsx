import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api, getErrorMessage } from '../lib/api';
import { clearSession } from '../lib/storage';
import { hasConfigValues, stripMaskedFields } from '../lib/connector';
import { Banner, Button } from '../components/ui';
import { colors } from '../theme';
import { styles } from './AdminScreen.styles';
import { DashboardTab, OrganizationsTab, UsersTab } from './admin/Tabs';
import OrganizationForm from './admin/OrganizationForm';
import UserForm from './admin/UserForm';
import ResetPasswordModal from './admin/ResetPasswordModal';
import FormModal from './admin/FormModal';

const TABS = ['Dashboard', 'Create Org', 'Create User', 'Organizations', 'Users'];
const EMPTY_ORG = { name: '', industry: '', connector_type: 'postgresql', connector_config: {} };
const EMPTY_USER = { email: '', password: '', org_id: '', role: 'user' };
const SUCCESS_MS = 4000;

export default function AdminScreen({ navigation }) {
  const [activeTab, setActiveTab] = useState('Dashboard');
  const [organizations, setOrganizations] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState({ kind: 'error', message: '' });
  const [formKey, setFormKey] = useState(0); // bump to reset a create form after success

  const [editOrg, setEditOrg] = useState(null);
  const [editUser, setEditUser] = useState(null);
  const [resetPwUser, setResetPwUser] = useState(null);

  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  const showFeedback = useCallback((message, isError = false) => {
    clearTimeout(timer.current);
    setFeedback({ kind: isError ? 'error' : 'success', message });
    // Errors stay until the next action so they can be read (and announced).
    if (!isError) timer.current = setTimeout(() => setFeedback({ kind: 'success', message: '' }), SUCCESS_MS);
  }, []);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const res = await api.get('/admin/dashboard');
      setOrganizations(res.data.organizations || []);
      setUsers(res.data.users || []);
    } catch (err) {
      setLoadError(getErrorMessage(err, 'Failed to load dashboard.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const handleLogout = async () => {
    await clearSession();
    navigation.replace('Login');
  };

  // Runs a mutation with the shared busy flag + feedback. Returns true on success.
  const runAction = async (request, success, failure) => {
    setBusy(true);
    showFeedback('', false);
    try {
      const res = await request();
      showFeedback(typeof success === 'function' ? success(res) : success);
      loadDashboard();
      return true;
    } catch (err) {
      showFeedback(getErrorMessage(err, failure), true);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const handleCreateOrg = async (form) => {
    const ok = await runAction(
      () =>
        api.post('/admin/organizations', {
          ...form,
          connector_config: form.connector_type === 'internal' ? {} : stripMaskedFields(form.connector_config),
        }),
      (res) => `Organization "${res.data.organization.name}" created.`,
      'Failed to create organization.',
    );
    if (ok) setFormKey((k) => k + 1);
  };

  const handleUpdateOrg = async (form) => {
    const payload = { name: form.name, industry: form.industry, connector_type: form.connector_type };
    // Stored secrets are never returned, so send a config only when the admin typed
    // one (or switched type); an untouched form must not wipe the stored credentials.
    const config = form.connector_type === 'internal' ? {} : stripMaskedFields(form.connector_config);
    const typeChanged = form.connector_type !== editOrg.connector_type;
    if (form.connector_type === 'internal' ? typeChanged : hasConfigValues(config) || typeChanged) {
      payload.connector_config = config;
    }
    const ok = await runAction(
      () => api.put(`/admin/organizations/${editOrg.id}`, payload),
      'Organization updated.',
      'Failed to update organization.',
    );
    if (ok) setEditOrg(null);
  };

  const handleCreateUser = async (form) => {
    const ok = await runAction(
      () => api.post('/admin/users', { ...form, email: form.email.trim() }),
      (res) => `User "${res.data.user.email}" created.`,
      'Failed to create user.',
    );
    if (ok) setFormKey((k) => k + 1);
  };

  const handleUpdateUser = async (form) => {
    const ok = await runAction(
      () => api.put(`/admin/users/${editUser.id}`, { email: form.email.trim(), role: form.role, org_id: form.org_id || null }),
      'User updated.',
      'Failed to update user.',
    );
    if (ok) setEditUser(null);
  };

  const handleResetPassword = async (password) => {
    const target = resetPwUser;
    const ok = await runAction(
      () => api.put(`/admin/users/${target.id}/reset-password`, { password }),
      `Password reset for ${target.email}.`,
      'Failed to reset password.',
    );
    if (ok) setResetPwUser(null);
  };

  const confirmDelete = (title, message, onConfirm) => {
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: onConfirm },
    ]);
  };

  const handleDeleteOrg = (org) =>
    confirmDelete('Delete organization', `Delete "${org.name}"? This will also delete all its users.`, () =>
      runAction(() => api.delete(`/admin/organizations/${org.id}`), 'Organization deleted.', 'Failed to delete organization.'),
    );

  const handleDeleteUser = (u) =>
    confirmDelete('Delete user', `Delete ${u.email}?`, () =>
      runAction(() => api.delete(`/admin/users/${u.id}`), 'User deleted.', 'Failed to delete user.'),
    );

  // The page banner sits behind an open modal, so errors are repeated inside it.
  const modalOpen = !!(editOrg || editUser || resetPwUser);
  const modalError = modalOpen && feedback.kind === 'error' ? feedback.message : '';

  const renderTabContent = () => {
    switch (activeTab) {
      case 'Dashboard':
        return (
          <DashboardTab
            organizations={organizations}
            users={users}
            loading={loading}
            loadError={loadError}
            onRefresh={loadDashboard}
          />
        );
      case 'Create Org':
        return (
          <ScrollView contentContainerStyle={styles.tabContent} keyboardShouldPersistTaps="handled">
            <Text style={styles.sectionTitle} accessibilityRole="header">New organization</Text>
            <OrganizationForm key={formKey} mode="create" initial={EMPTY_ORG} busy={busy} onSubmit={handleCreateOrg} />
          </ScrollView>
        );
      case 'Create User':
        return (
          <ScrollView contentContainerStyle={styles.tabContent} keyboardShouldPersistTaps="handled">
            <Text style={styles.sectionTitle} accessibilityRole="header">New user</Text>
            <UserForm key={formKey} mode="create" initial={EMPTY_USER} organizations={organizations} busy={busy} onSubmit={handleCreateUser} />
          </ScrollView>
        );
      case 'Organizations':
        return (
          <OrganizationsTab
            organizations={organizations}
            loading={loading}
            onRefresh={loadDashboard}
            onEdit={setEditOrg}
            onDelete={handleDeleteOrg}
          />
        );
      case 'Users':
        return (
          <UsersTab
            users={users}
            organizations={organizations}
            loading={loading}
            onRefresh={loadDashboard}
            onEdit={setEditUser}
            onResetPassword={setResetPwUser}
            onDelete={handleDeleteUser}
          />
        );
      default:
        return null;
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle} accessibilityRole="header">Admin Panel</Text>
        <Button label="Logout" variant="secondary" onPress={handleLogout} style={styles.logoutBtn} accessibilityHint="Signs out and returns to the login screen" />
      </View>

      <View style={styles.banners}>
        <Banner kind={feedback.kind} message={modalOpen && feedback.kind === 'error' ? '' : feedback.message} />
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.tabBar}
        contentContainerStyle={styles.tabBarContent}
        accessibilityRole="tablist"
      >
        {TABS.map((tab) => {
          const selected = activeTab === tab;
          return (
            <TouchableOpacity
              key={tab}
              style={[styles.tab, selected && styles.tabActive]}
              onPress={() => setActiveTab(tab)}
              accessibilityRole="tab"
              accessibilityLabel={tab}
              accessibilityState={{ selected }}
            >
              <Text style={[styles.tabText, selected && styles.tabTextActive]}>{tab}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {loading && activeTab === 'Dashboard' && organizations.length === 0 && users.length === 0 ? (
          <View style={styles.loadingContainer} accessibilityLabel="Loading dashboard" accessibilityLiveRegion="polite">
            <ActivityIndicator size="large" color={colors.primary} />
          </View>
        ) : (
          renderTabContent()
        )}
      </KeyboardAvoidingView>

      {editOrg && (
        <FormModal visible title="Edit organization" error={modalError} onClose={() => setEditOrg(null)}>
          <OrganizationForm
            mode="edit"
            initial={{ name: editOrg.name || '', industry: editOrg.industry || '', connector_type: editOrg.connector_type, connector_config: {} }}
            busy={busy}
            onSubmit={handleUpdateOrg}
            onCancel={() => setEditOrg(null)}
          />
        </FormModal>
      )}

      {editUser && (
        <FormModal visible title="Edit user" error={modalError} onClose={() => setEditUser(null)}>
          <UserForm
            mode="edit"
            initial={{ email: editUser.email, role: editUser.role, org_id: editUser.org_id || '' }}
            organizations={organizations}
            busy={busy}
            onSubmit={handleUpdateUser}
            onCancel={() => setEditUser(null)}
          />
        </FormModal>
      )}

      {resetPwUser && (
        <ResetPasswordModal user={resetPwUser} busy={busy} error={modalError} onSubmit={handleResetPassword} onClose={() => setResetPwUser(null)} />
      )}
    </SafeAreaView>
  );
}
