import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Alert,
  Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '../lib/api';
import { storage } from '../lib/storage';
import { styles } from './AdminScreen.styles';

const CONNECTOR_CONFIG_FIELDS = {
  postgresql: [
    { field: 'host', label: 'Host', placeholder: 'db.example.com' },
    { field: 'port', label: 'Port', placeholder: '5432', keyboardType: 'numeric' },
    { field: 'database', label: 'Database', placeholder: 'my_database' },
    { field: 'user', label: 'Username', placeholder: 'postgres' },
    { field: 'password', label: 'Password', placeholder: '••••••••', secure: true },
  ],
  mysql: [
    { field: 'host', label: 'Host', placeholder: 'db.example.com' },
    { field: 'port', label: 'Port', placeholder: '3306', keyboardType: 'numeric' },
    { field: 'database', label: 'Database', placeholder: 'my_database' },
    { field: 'user', label: 'Username', placeholder: 'root' },
    { field: 'password', label: 'Password', placeholder: '••••••••', secure: true },
  ],
  hubspot: [
    { field: 'api_key', label: 'API Key', placeholder: 'Your HubSpot API Key', secure: true },
  ],
  salesforce: [
    { field: 'client_id', label: 'Client ID', placeholder: 'Your Salesforce Client ID' },
    { field: 'client_secret', label: 'Client Secret', placeholder: '••••••••', secure: true },
    { field: 'username', label: 'Username', placeholder: 'user@example.com' },
    { field: 'password', label: 'Password', placeholder: '••••••••', secure: true },
  ],
  dynamics: [
    { field: 'tenant_id', label: 'Tenant ID', placeholder: 'Your Azure Tenant ID' },
    { field: 'client_id', label: 'Client ID', placeholder: 'Your Client ID' },
    { field: 'client_secret', label: 'Client Secret', placeholder: '••••••••', secure: true },
    { field: 'dynamics_url', label: 'Dynamics URL', placeholder: 'https://yourorg.crm.dynamics.com' },
  ],
};

const TABS = ['Dashboard', 'Create Org', 'Create User', 'Organizations', 'Users'];

export default function AdminScreen({ navigation }) {
  const [user, setUser] = useState(null);
  const [activeTab, setActiveTab] = useState('Dashboard');
  const [organizations, setOrganizations] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Create org form
  const [newOrg, setNewOrg] = useState({ name: '', industry: '', connector_type: 'postgresql', connector_config: {} });

  // Create user form
  const [newUser, setNewUser] = useState({ email: '', password: '', org_id: '', role: 'user' });

  // Edit modals
  const [editOrgModal, setEditOrgModal] = useState(null); // org object
  const [editUserModal, setEditUserModal] = useState(null); // user object
  const [resetPwModal, setResetPwModal] = useState(null); // user object
  const [newPassword, setNewPassword] = useState('');

  useEffect(() => {
    storage.getItem('user').then((str) => {
      if (str) setUser(JSON.parse(str));
    });
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/admin/dashboard');
      setOrganizations(res.data.organizations || []);
      setUsers(res.data.users || []);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load dashboard.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    await storage.removeItem('token');
    await storage.removeItem('user');
    navigation.replace('Login');
  };

  const showFeedback = (msg, isError = false) => {
    if (isError) setError(msg);
    else setSuccess(msg);
    setTimeout(() => { setError(''); setSuccess(''); }, 3000);
  };

  // ── Create Org ──
  const handleCreateOrg = async () => {
    if (!newOrg.name.trim()) { showFeedback('Organization name is required.', true); return; }
    setLoading(true);
    try {
      const res = await api.post('/admin/organizations', newOrg);
      showFeedback(`Organization "${res.data.organization.name}" created.`);
      setNewOrg({ name: '', industry: '', connector_type: 'postgresql', connector_config: {} });
      loadDashboard();
    } catch (err) {
      showFeedback(err.response?.data?.error || 'Failed to create organization.', true);
    } finally {
      setLoading(false);
    }
  };

  // ── Create User ──
  const handleCreateUser = async () => {
    if (!newUser.email.trim() || !newUser.password.trim()) {
      showFeedback('Email and password are required.', true); return;
    }
    setLoading(true);
    try {
      const res = await api.post('/admin/users', newUser);
      showFeedback(`User "${res.data.user.email}" created.`);
      setNewUser({ email: '', password: '', org_id: '', role: 'user' });
      loadDashboard();
    } catch (err) {
      showFeedback(err.response?.data?.error || 'Failed to create user.', true);
    } finally {
      setLoading(false);
    }
  };

  // ── Delete org ──
  const handleDeleteOrg = (org) => {
    Alert.alert(
      'Delete Organization',
      `Delete "${org.name}"? This will also delete all its users.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete', style: 'destructive', onPress: async () => {
            try {
              await api.delete(`/admin/organizations/${org.id}`);
              showFeedback('Organization deleted.');
              loadDashboard();
            } catch (err) {
              showFeedback(err.response?.data?.error || 'Failed to delete.', true);
            }
          },
        },
      ]
    );
  };

  // ── Delete user ──
  const handleDeleteUser = (u) => {
    Alert.alert('Delete User', `Delete ${u.email}?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete', style: 'destructive', onPress: async () => {
          try {
            await api.delete(`/admin/users/${u.id}`);
            showFeedback('User deleted.');
            loadDashboard();
          } catch (err) {
            showFeedback(err.response?.data?.error || 'Failed to delete.', true);
          }
        },
      },
    ]);
  };

  // ── Save edit org ──
  const handleSaveEditOrg = async () => {
    if (!editOrgModal) return;
    try {
      await api.put(`/admin/organizations/${editOrgModal.id}`, {
        name: editOrgModal.name,
        industry: editOrgModal.industry,
        connector_type: editOrgModal.connector_type,
        // Omitted unless edited: the dashboard never returns stored credentials, and sending {}
        // would wipe them.
        ...(editOrgModal.connector_config ? { connector_config: editOrgModal.connector_config } : {}),
      });
      showFeedback('Organization updated.');
      setEditOrgModal(null);
      loadDashboard();
    } catch (err) {
      showFeedback(err.response?.data?.error || 'Failed to update.', true);
    }
  };

  // ── Save edit user ──
  const handleSaveEditUser = async () => {
    if (!editUserModal) return;
    try {
      await api.put(`/admin/users/${editUserModal.id}`, {
        email: editUserModal.email,
        role: editUserModal.role,
        org_id: editUserModal.org_id || null,
      });
      showFeedback('User updated.');
      setEditUserModal(null);
      loadDashboard();
    } catch (err) {
      showFeedback(err.response?.data?.error || 'Failed to update.', true);
    }
  };

  // ── Reset password ──
  const handleResetPassword = async () => {
    if (!resetPwModal || !newPassword.trim()) {
      showFeedback('New password is required.', true); return;
    }
    try {
      await api.put(`/admin/users/${resetPwModal.id}/reset-password`, { password: newPassword });
      showFeedback(`Password reset for ${resetPwModal.email}.`);
      setResetPwModal(null);
      setNewPassword('');
    } catch (err) {
      showFeedback(err.response?.data?.error || 'Failed to reset password.', true);
    }
  };

  const orgName = (orgId) => organizations.find((o) => o.id === orgId)?.name || '—';

  // ── Render helpers ──

  const ConnectorFields = ({ connectorType, config, onChange }) => {
    const fields = CONNECTOR_CONFIG_FIELDS[connectorType] || [];
    return (
      <View>
        {fields.map((f) => (
          <View key={f.field} style={styles.formGroup}>
            <Text style={styles.label}>{f.label}</Text>
            <TextInput
              style={styles.input}
              value={String(config[f.field] || '')}
              onChangeText={(v) => onChange({ ...config, [f.field]: v })}
              placeholder={f.placeholder}
              placeholderTextColor="#555"
              secureTextEntry={!!f.secure}
              keyboardType={f.keyboardType || 'default'}
              autoCapitalize="none"
            />
          </View>
        ))}
      </View>
    );
  };

  const CONNECTOR_TYPES = ['postgresql', 'mysql', 'hubspot', 'salesforce', 'dynamics', 'internal'];
  const ROLES = ['user', 'owner', 'admin'];

  const renderTabContent = () => {
    switch (activeTab) {
      case 'Dashboard':
        return (
          <ScrollView contentContainerStyle={styles.tabContent}>
            <View style={styles.statsRow}>
              <View style={styles.statCard}>
                <Text style={styles.statNumber}>{organizations.length}</Text>
                <Text style={styles.statLabel}>Organizations</Text>
              </View>
              <View style={styles.statCard}>
                <Text style={styles.statNumber}>{users.length}</Text>
                <Text style={styles.statLabel}>Users</Text>
              </View>
            </View>
            <TouchableOpacity style={styles.refreshBtn} onPress={loadDashboard} disabled={loading}>
              <Text style={styles.refreshBtnText}>{loading ? 'Refreshing...' : '↻ Refresh'}</Text>
            </TouchableOpacity>
          </ScrollView>
        );

      case 'Create Org':
        return (
          <ScrollView contentContainerStyle={styles.tabContent} keyboardShouldPersistTaps="handled">
            <Text style={styles.sectionTitle}>New Organization</Text>
            <View style={styles.formGroup}>
              <Text style={styles.label}>Name *</Text>
              <TextInput style={styles.input} value={newOrg.name} onChangeText={(v) => setNewOrg((p) => ({ ...p, name: v }))} placeholder="Acme Corp" placeholderTextColor="#555" />
            </View>
            <View style={styles.formGroup}>
              <Text style={styles.label}>Industry</Text>
              <TextInput style={styles.input} value={newOrg.industry} onChangeText={(v) => setNewOrg((p) => ({ ...p, industry: v }))} placeholder="medical / legal / sales…" placeholderTextColor="#555" />
            </View>
            <View style={styles.formGroup}>
              <Text style={styles.label}>Connector Type</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
                {CONNECTOR_TYPES.map((ct) => (
                  <TouchableOpacity
                    key={ct}
                    style={[styles.chip, newOrg.connector_type === ct && styles.chipActive]}
                    onPress={() => setNewOrg((p) => ({ ...p, connector_type: ct, connector_config: {} }))}
                  >
                    <Text style={[styles.chipText, newOrg.connector_type === ct && styles.chipTextActive]}>{ct}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
            {newOrg.connector_type !== 'internal' && (
              <ConnectorFields
                connectorType={newOrg.connector_type}
                config={newOrg.connector_config}
                onChange={(cfg) => setNewOrg((p) => ({ ...p, connector_config: cfg }))}
              />
            )}
            <TouchableOpacity style={styles.submitBtn} onPress={handleCreateOrg} disabled={loading}>
              <Text style={styles.submitBtnText}>{loading ? 'Creating…' : 'Create Organization'}</Text>
            </TouchableOpacity>
          </ScrollView>
        );

      case 'Create User':
        return (
          <ScrollView contentContainerStyle={styles.tabContent} keyboardShouldPersistTaps="handled">
            <Text style={styles.sectionTitle}>New User</Text>
            <View style={styles.formGroup}>
              <Text style={styles.label}>Email *</Text>
              <TextInput style={styles.input} value={newUser.email} onChangeText={(v) => setNewUser((p) => ({ ...p, email: v }))} placeholder="user@example.com" placeholderTextColor="#555" keyboardType="email-address" autoCapitalize="none" />
            </View>
            <View style={styles.formGroup}>
              <Text style={styles.label}>Password *</Text>
              <TextInput style={styles.input} value={newUser.password} onChangeText={(v) => setNewUser((p) => ({ ...p, password: v }))} placeholder="••••••••" placeholderTextColor="#555" secureTextEntry />
            </View>
            <View style={styles.formGroup}>
              <Text style={styles.label}>Organization</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
                <TouchableOpacity
                  style={[styles.chip, !newUser.org_id && styles.chipActive]}
                  onPress={() => setNewUser((p) => ({ ...p, org_id: '' }))}
                >
                  <Text style={[styles.chipText, !newUser.org_id && styles.chipTextActive]}>None</Text>
                </TouchableOpacity>
                {organizations.map((o) => (
                  <TouchableOpacity
                    key={o.id}
                    style={[styles.chip, newUser.org_id === o.id && styles.chipActive]}
                    onPress={() => setNewUser((p) => ({ ...p, org_id: o.id }))}
                  >
                    <Text style={[styles.chipText, newUser.org_id === o.id && styles.chipTextActive]}>{o.name}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
            <View style={styles.formGroup}>
              <Text style={styles.label}>Role</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
                {ROLES.map((r) => (
                  <TouchableOpacity
                    key={r}
                    style={[styles.chip, newUser.role === r && styles.chipActive]}
                    onPress={() => setNewUser((p) => ({ ...p, role: r }))}
                  >
                    <Text style={[styles.chipText, newUser.role === r && styles.chipTextActive]}>{r}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
            <TouchableOpacity style={styles.submitBtn} onPress={handleCreateUser} disabled={loading}>
              <Text style={styles.submitBtnText}>{loading ? 'Creating…' : 'Create User'}</Text>
            </TouchableOpacity>
          </ScrollView>
        );

      case 'Organizations':
        return (
          <ScrollView contentContainerStyle={styles.tabContent}>
            <Text style={styles.sectionTitle}>Organizations ({organizations.length})</Text>
            {organizations.map((org) => (
              <View key={org.id} style={styles.card}>
                <View style={styles.cardRow}>
                  <Text style={styles.cardTitle}>{org.name}</Text>
                  <Text style={styles.badge}>{org.connector_type}</Text>
                </View>
                {org.industry ? <Text style={styles.cardSub}>{org.industry}</Text> : null}
                <View style={styles.cardActions}>
                  <TouchableOpacity
                    style={styles.cardBtn}
                    onPress={() => setEditOrgModal({ ...org, connector_config: org.connector_config || {} })}
                  >
                    <Text style={styles.cardBtnText}>Edit</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.cardBtn, styles.cardBtnDanger]} onPress={() => handleDeleteOrg(org)}>
                    <Text style={[styles.cardBtnText, styles.cardBtnTextDanger]}>Delete</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </ScrollView>
        );

      case 'Users':
        return (
          <ScrollView contentContainerStyle={styles.tabContent}>
            <Text style={styles.sectionTitle}>Users ({users.length})</Text>
            {users.map((u) => (
              <View key={u.id} style={styles.card}>
                <View style={styles.cardRow}>
                  <Text style={styles.cardTitle} numberOfLines={1}>{u.email}</Text>
                  <Text style={styles.badge}>{u.role}</Text>
                </View>
                <Text style={styles.cardSub}>Org: {orgName(u.org_id)}</Text>
                <View style={styles.cardActions}>
                  <TouchableOpacity style={styles.cardBtn} onPress={() => setEditUserModal({ ...u })}>
                    <Text style={styles.cardBtnText}>Edit</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.cardBtn} onPress={() => { setResetPwModal(u); setNewPassword(''); }}>
                    <Text style={styles.cardBtnText}>Reset PW</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.cardBtn, styles.cardBtnDanger]} onPress={() => handleDeleteUser(u)}>
                    <Text style={[styles.cardBtnText, styles.cardBtnTextDanger]}>Delete</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </ScrollView>
        );

      default:
        return null;
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Admin Panel</Text>
        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
          <Text style={styles.logoutBtnText}>Logout</Text>
        </TouchableOpacity>
      </View>

      {/* Alert banners */}
      {!!error && (
        <View style={styles.alertError}>
          <Text style={styles.alertText}>{error}</Text>
        </View>
      )}
      {!!success && (
        <View style={styles.alertSuccess}>
          <Text style={styles.alertText}>{success}</Text>
        </View>
      )}

      {/* Tab bar */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabBar} contentContainerStyle={styles.tabBarContent}>
        {TABS.map((tab) => (
          <TouchableOpacity
            key={tab}
            style={[styles.tab, activeTab === tab && styles.tabActive]}
            onPress={() => setActiveTab(tab)}
          >
            <Text style={[styles.tabText, activeTab === tab && styles.tabTextActive]}>{tab}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Content */}
      <View style={styles.flex}>
        {loading && activeTab === 'Dashboard' ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#667eea" />
          </View>
        ) : (
          renderTabContent()
        )}
      </View>

      {/* ── Edit Org Modal ── */}
      <Modal visible={!!editOrgModal} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalBox}>
            <Text style={styles.modalTitle}>Edit Organization</Text>
            <ScrollView keyboardShouldPersistTaps="handled">
              <View style={styles.formGroup}>
                <Text style={styles.label}>Name *</Text>
                <TextInput style={styles.input} value={editOrgModal?.name || ''} onChangeText={(v) => setEditOrgModal((p) => ({ ...p, name: v }))} placeholderTextColor="#555" />
              </View>
              <View style={styles.formGroup}>
                <Text style={styles.label}>Industry</Text>
                <TextInput style={styles.input} value={editOrgModal?.industry || ''} onChangeText={(v) => setEditOrgModal((p) => ({ ...p, industry: v }))} placeholderTextColor="#555" />
              </View>
              <View style={styles.formGroup}>
                <Text style={styles.label}>Connector Type</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
                  {CONNECTOR_TYPES.map((ct) => (
                    <TouchableOpacity
                      key={ct}
                      style={[styles.chip, editOrgModal?.connector_type === ct && styles.chipActive]}
                      onPress={() => setEditOrgModal((p) => ({ ...p, connector_type: ct, connector_config: {} }))}
                    >
                      <Text style={[styles.chipText, editOrgModal?.connector_type === ct && styles.chipTextActive]}>{ct}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </View>
              {editOrgModal?.connector_type !== 'internal' && (
                <ConnectorFields
                  connectorType={editOrgModal?.connector_type || 'postgresql'}
                  config={editOrgModal?.connector_config || {}}
                  onChange={(cfg) => setEditOrgModal((p) => ({ ...p, connector_config: cfg }))}
                />
              )}
            </ScrollView>
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.modalCancelBtn} onPress={() => setEditOrgModal(null)}>
                <Text style={styles.modalCancelBtnText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.submitBtn} onPress={handleSaveEditOrg}>
                <Text style={styles.submitBtnText}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* ── Edit User Modal ── */}
      <Modal visible={!!editUserModal} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalBox}>
            <Text style={styles.modalTitle}>Edit User</Text>
            <View style={styles.formGroup}>
              <Text style={styles.label}>Email</Text>
              <TextInput style={styles.input} value={editUserModal?.email || ''} onChangeText={(v) => setEditUserModal((p) => ({ ...p, email: v }))} keyboardType="email-address" autoCapitalize="none" placeholderTextColor="#555" />
            </View>
            <View style={styles.formGroup}>
              <Text style={styles.label}>Role</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
                {ROLES.map((r) => (
                  <TouchableOpacity key={r} style={[styles.chip, editUserModal?.role === r && styles.chipActive]} onPress={() => setEditUserModal((p) => ({ ...p, role: r }))}>
                    <Text style={[styles.chipText, editUserModal?.role === r && styles.chipTextActive]}>{r}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
            <View style={styles.formGroup}>
              <Text style={styles.label}>Organization</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
                <TouchableOpacity style={[styles.chip, !editUserModal?.org_id && styles.chipActive]} onPress={() => setEditUserModal((p) => ({ ...p, org_id: '' }))}>
                  <Text style={[styles.chipText, !editUserModal?.org_id && styles.chipTextActive]}>None</Text>
                </TouchableOpacity>
                {organizations.map((o) => (
                  <TouchableOpacity key={o.id} style={[styles.chip, editUserModal?.org_id === o.id && styles.chipActive]} onPress={() => setEditUserModal((p) => ({ ...p, org_id: o.id }))}>
                    <Text style={[styles.chipText, editUserModal?.org_id === o.id && styles.chipTextActive]}>{o.name}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.modalCancelBtn} onPress={() => setEditUserModal(null)}>
                <Text style={styles.modalCancelBtnText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.submitBtn} onPress={handleSaveEditUser}>
                <Text style={styles.submitBtnText}>Save</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* ── Reset Password Modal ── */}
      <Modal visible={!!resetPwModal} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalBox}>
            <Text style={styles.modalTitle}>Reset Password</Text>
            <Text style={styles.modalSubtitle}>{resetPwModal?.email}</Text>
            <View style={styles.formGroup}>
              <Text style={styles.label}>New Password</Text>
              <TextInput style={styles.input} value={newPassword} onChangeText={setNewPassword} secureTextEntry placeholder="••••••••" placeholderTextColor="#555" />
            </View>
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.modalCancelBtn} onPress={() => { setResetPwModal(null); setNewPassword(''); }}>
                <Text style={styles.modalCancelBtnText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.submitBtn} onPress={handleResetPassword}>
                <Text style={styles.submitBtnText}>Reset</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}


