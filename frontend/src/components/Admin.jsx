import PropTypes from 'prop-types';
import { useCallback, useEffect, useState } from 'react';
import { api, getErrorMessage } from '../lib/api';
import { stripMaskedFields } from '../lib/connector';
import ConfirmDialog from './ConfirmDialog';
import DashboardTab from './admin/DashboardTab';
import OrganizationForm from './admin/OrganizationForm';
import OrganizationsTab from './admin/OrganizationsTab';
import ResetPasswordDialog from './admin/ResetPasswordDialog';
import UserForm from './admin/UserForm';
import UsersTab from './admin/UsersTab';

const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'create-org', label: 'Create organization' },
  { id: 'create-user', label: 'Create user' },
  { id: 'manage-users', label: 'Manage users' },
  { id: 'organizations', label: 'Organizations' },
];

const EMPTY_ORG = { name: '', industry: '', connector_type: 'internal', connector_config: {} };
const EMPTY_USER = { email: '', password: '', org_id: '', role: 'user' };

export default function Admin({ user, onLogout }) {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [organizations, setOrganizations] = useState([]);
  const [users, setUsers] = useState([]);
  const [loadingData, setLoadingData] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [busy, setBusy] = useState(false); // a create/update/delete request is in flight
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [orgFilter, setOrgFilter] = useState('');
  const [formKey, setFormKey] = useState(0); // remounts create forms after success to clear them

  const [editingOrg, setEditingOrg] = useState(null); // organization object being edited
  const [editingUser, setEditingUser] = useState(null);
  const [resetUser, setResetUser] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null); // {kind: 'user' | 'org', id, label}

  const loadDashboard = useCallback(async () => {
    setLoadingData(true);
    setLoadError('');
    try {
      const response = await api.get('/admin/dashboard');
      setOrganizations(response.data.organizations || []);
      setUsers(response.data.users || []);
    } catch (err) {
      setLoadError(getErrorMessage(err, 'Failed to load the dashboard.'));
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const goToTab = (tab) => {
    setActiveTab(tab);
    setError('');
    setSuccess('');
  };

  // Runs a mutation with shared busy/error/success handling. Returns true on success.
  const runAction = async (action, successMessage, failureMessage) => {
    setBusy(true);
    setError('');
    setSuccess('');
    try {
      const result = await action();
      setSuccess(typeof successMessage === 'function' ? successMessage(result) : successMessage);
      loadDashboard();
      return true;
    } catch (err) {
      setError(getErrorMessage(err, failureMessage));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const handleCreateOrganization = async (form) => {
    const payload = {
      ...form,
      connector_config: form.connector_type === 'internal' ? {} : stripMaskedFields(form.connector_config),
    };
    const ok = await runAction(
      () => api.post('/admin/organizations', payload),
      (res) => `Organization "${res.data.organization.name}" created successfully.`,
      'Failed to create organization.',
    );
    if (ok) setFormKey((k) => k + 1);
  };

  const handleUpdateOrganization = async (form) => {
    const payload = {
      name: form.name,
      industry: form.industry,
      connector_type: form.connector_type,
    };
    // Stored secrets are never shown; send a config only when the admin actually typed one
    // (or switched type), so an untouched form cannot wipe the stored credentials.
    const config = form.connector_type === 'internal' ? {} : stripMaskedFields(form.connector_config);
    const typeChanged = form.connector_type !== editingOrg.connector_type;
    const hasValues = Object.values(config).some((v) => String(v).trim() !== '');
    if (form.connector_type === 'internal' ? typeChanged : hasValues || typeChanged) {
      payload.connector_config = config;
    }
    const ok = await runAction(
      () => api.put(`/admin/organizations/${editingOrg.id}`, payload),
      'Organization updated successfully.',
      'Failed to update organization.',
    );
    if (ok) {
      setEditingOrg(null);
      setActiveTab('organizations');
    }
  };

  const handleCreateUser = async (form) => {
    const ok = await runAction(
      () => api.post('/admin/users', form),
      (res) => `User "${res.data.user.email}" created successfully.`,
      'Failed to create user.',
    );
    if (ok) setFormKey((k) => k + 1);
  };

  const handleUpdateUser = async (form) => {
    const ok = await runAction(
      () => api.put(`/admin/users/${editingUser.id}`, { email: form.email, role: form.role, org_id: form.org_id }),
      'User updated successfully.',
      'Failed to update user.',
    );
    if (ok) {
      setEditingUser(null);
      setActiveTab('manage-users');
    }
  };

  const handleResetPassword = async (password) => {
    const target = resetUser;
    const ok = await runAction(
      () => api.put(`/admin/users/${target.id}/reset-password`, { password }),
      `Password reset successfully for ${target.email}.`,
      'Failed to reset password.',
    );
    if (ok) setResetUser(null);
  };

  const confirmDelete = async () => {
    const target = pendingDelete;
    const isUser = target.kind === 'user';
    await runAction(
      () => api.delete(isUser ? `/admin/users/${target.id}` : `/admin/organizations/${target.id}`),
      isUser ? 'User deleted successfully.' : 'Organization deleted successfully.',
      isUser ? 'Failed to delete user.' : 'Failed to delete organization.',
    );
    setPendingDelete(null);
  };

  const startEditOrganization = (org) => {
    setEditingOrg(org);
    goToTab('edit-org');
  };

  const startEditUser = (u) => {
    setEditingUser(u);
    goToTab('edit-user');
  };

  const tabs = [
    ...TABS,
    ...(editingOrg ? [{ id: 'edit-org', label: 'Edit organization' }] : []),
    ...(editingUser ? [{ id: 'edit-user', label: 'Edit user' }] : []),
  ];

  const headings = {
    dashboard: 'Dashboard',
    'create-org': 'Create new organization',
    'create-user': 'Create new user',
    'manage-users': 'Manage users',
    organizations: 'All organizations',
    'edit-org': 'Edit organization',
    'edit-user': 'Edit user',
  };

  return (
    <div className="page on-gradient">
      <a className="skip-link" href="#main">Skip to main content</a>

      <header className="app-header">
        <h1>Lia administration</h1>
        <div className="app-header-actions">
          <span>
            Signed in as <strong>{user.email}</strong> ({user.role})
          </span>
          <button type="button" onClick={onLogout} className="btn btn-ghost">Log out</button>
        </div>
      </header>

      <nav className="app-nav" aria-label="Admin sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className="tab-btn"
            aria-current={activeTab === tab.id ? 'page' : undefined}
            onClick={() => goToTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main className="page-main" id="main" tabIndex={-1}>
        {/* Live regions stay mounted so screen readers announce what appears inside them. */}
        <div role="alert" className="alert-slot">
          {error && <div className="alert alert-error">{error}</div>}
          {loadError && (
            <div className="alert alert-error">
              {loadError}{' '}
              <button type="button" className="btn btn-secondary btn-sm" onClick={loadDashboard}>
                Try again
              </button>
            </div>
          )}
        </div>
        <div role="status" className="alert-slot">
          {success && <div className="alert alert-success">{success}</div>}
        </div>

        <section className="panel" aria-labelledby="panel-title" aria-busy={loadingData}>
          <h2 id="panel-title">{headings[activeTab]}</h2>

          {activeTab === 'dashboard' && (
            <DashboardTab organizations={organizations} users={users} loading={loadingData} />
          )}

          {activeTab === 'create-org' && (
            <OrganizationForm key={formKey} mode="create" initial={EMPTY_ORG} busy={busy} onSubmit={handleCreateOrganization} />
          )}

          {activeTab === 'create-user' && (
            <UserForm
              key={formKey}
              mode="create"
              initial={EMPTY_USER}
              organizations={organizations}
              busy={busy}
              onSubmit={handleCreateUser}
            />
          )}

          {activeTab === 'manage-users' && (
            <UsersTab
              users={users}
              organizations={organizations}
              orgFilter={orgFilter}
              onFilterChange={setOrgFilter}
              loading={loadingData}
              onEdit={startEditUser}
              onResetPassword={setResetUser}
              onDelete={(u) => setPendingDelete({ kind: 'user', id: u.id, label: u.email })}
            />
          )}

          {activeTab === 'organizations' && (
            <OrganizationsTab
              organizations={organizations}
              loading={loadingData}
              onEdit={startEditOrganization}
              onDelete={(org) => setPendingDelete({ kind: 'org', id: org.id, label: org.name })}
            />
          )}

          {activeTab === 'edit-org' && editingOrg && (
            <OrganizationForm
              key={editingOrg.id}
              mode="edit"
              initial={{
                name: editingOrg.name,
                industry: editingOrg.industry || '',
                connector_type: editingOrg.connector_type,
                connector_config: {},
              }}
              busy={busy}
              onSubmit={handleUpdateOrganization}
              onCancel={() => {
                setEditingOrg(null);
                goToTab('organizations');
              }}
            />
          )}

          {activeTab === 'edit-user' && editingUser && (
            <UserForm
              key={editingUser.id}
              mode="edit"
              initial={{ email: editingUser.email, role: editingUser.role, org_id: editingUser.org_id || '' }}
              organizations={organizations}
              busy={busy}
              onSubmit={handleUpdateUser}
              onCancel={() => {
                setEditingUser(null);
                goToTab('manage-users');
              }}
            />
          )}
        </section>
      </main>

      {resetUser && (
        <ResetPasswordDialog user={resetUser} busy={busy} onSubmit={handleResetPassword} onCancel={() => setResetUser(null)} />
      )}

      {pendingDelete && (
        <ConfirmDialog
          title={pendingDelete.kind === 'user' ? 'Delete user?' : 'Delete organization?'}
          message={
            pendingDelete.kind === 'user'
              ? `${pendingDelete.label} will be permanently deleted. This cannot be undone.`
              : `"${pendingDelete.label}" and all users in this organization will be permanently deleted. This cannot be undone.`
          }
          busy={busy}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}

Admin.propTypes = { user: PropTypes.shape({ email: PropTypes.string, role: PropTypes.string }).isRequired, onLogout: PropTypes.func.isRequired };
