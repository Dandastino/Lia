import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import './Admin.css';

// Connector config field templates
const CONNECTOR_CONFIG_TEMPLATES = {
  postgresql: [
    { field: 'host', label: 'Host', type: 'text', placeholder: 'db.example.com', required: true },
    { field: 'port', label: 'Port', type: 'number', placeholder: '5432', required: false },
    { field: 'database', label: 'Database', type: 'text', placeholder: 'my_database', required: true },
    { field: 'user', label: 'Username', type: 'text', placeholder: 'postgres', required: true },
    { field: 'password', label: 'Password', type: 'password', placeholder: '••••••••', required: true },
  ],
  mysql: [
    { field: 'host', label: 'Host', type: 'text', placeholder: 'db.example.com', required: true },
    { field: 'port', label: 'Port', type: 'number', placeholder: '3306', required: false },
    { field: 'database', label: 'Database', type: 'text', placeholder: 'my_database', required: true },
    { field: 'user', label: 'Username', type: 'text', placeholder: 'root', required: true },
    { field: 'password', label: 'Password', type: 'password', placeholder: '••••••••', required: true },
  ],
  salesforce: [
    { field: 'client_id', label: 'Client ID', type: 'text', placeholder: 'Your Salesforce Client ID', required: true },
    { field: 'client_secret', label: 'Client Secret', type: 'password', placeholder: '••••••••', required: true },
    { field: 'username', label: 'Username', type: 'text', placeholder: 'user@example.com', required: true },
    { field: 'password', label: 'Password', type: 'password', placeholder: '••••••••', required: true },
  ],
  hubspot: [
    { field: 'api_key', label: 'API Key', type: 'password', placeholder: 'Your HubSpot API Key', required: true },
  ],
  dynamics: [
    { field: 'tenant_id', label: 'Tenant ID', type: 'text', placeholder: 'Your Azure Tenant ID', required: true },
    { field: 'client_id', label: 'Client ID', type: 'text', placeholder: 'Your Client ID', required: true },
    { field: 'client_secret', label: 'Client Secret', type: 'password', placeholder: '••••••••', required: true },
  ],
};

function ConnectorConfigForm({ connectorType, config, onChange }) {
  const fields = CONNECTOR_CONFIG_TEMPLATES[connectorType] || [];

  if (connectorType === 'internal') {
    return <p>No configuration needed for internal connector.</p>;
  }

  return (
    <div className="connector-config-group">
      <h4>{connectorType.charAt(0).toUpperCase() + connectorType.slice(1)} Configuration</h4>
      {fields.map((field) => (
        <div key={field.field} className="form-group">
          <label htmlFor={field.field}>
            {field.label} {field.required && '*'}
          </label>
          <input
            type={field.type}
            id={field.field}
            placeholder={field.placeholder}
            value={config[field.field] || ''}
            onChange={(e) =>
              onChange({
                ...config,
                [field.field]: e.target.value,
              })
            }
            required={field.required}
          />
        </div>
      ))}
    </div>
  );
}

export default function Admin({ user, onLogout }) {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [organizations, setOrganizations] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Filter state
  const [orgFilter, setOrgFilter] = useState(''); // Organization filter for users table

  // Password reset state
  const [resetPasswordUser, setResetPasswordUser] = useState(null);
  const [newPassword, setNewPassword] = useState('');

  // Form states
  const [newOrgForm, setNewOrgForm] = useState({
    name: '',
    industry: '',
    connector_type: 'internal',
    connector_config: {},
  });

  const [newUserForm, setNewUserForm] = useState({
    email: '',
    password: '',
    org_id: '',
    role: 'user',
  });

  // Edit states
  const [editingOrg, setEditingOrg] = useState(null);
  const [editingUser, setEditingUser] = useState(null);
  const [editOrgForm, setEditOrgForm] = useState({
    name: '',
    industry: '',
    connector_type: 'internal',
    connector_config: {},
  });
  const [editUserForm, setEditUserForm] = useState({
    email: '',
    role: 'user',
    org_id: '',
  });

  // Load dashboard data on mount
  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('/admin/dashboard');
      setOrganizations(response.data.organizations);
      setUsers(response.data.users);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateOrganization = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const payload = { ...newOrgForm };
      if (newOrgForm.connector_type === 'internal') {
        payload.connector_config = {};
      }
      const response = await api.post('/admin/organizations', payload);
      setSuccess(`Organization "${response.data.organization.name}" created successfully`);
      setNewOrgForm({ name: '', industry: '', connector_type: 'internal', connector_config: {} });
      loadDashboard();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to create organization');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateOrganization = async (e) => {
    e.preventDefault();
    if (!editingOrg) return;

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const payload = {
        name: editOrgForm.name,
        industry: editOrgForm.industry,
        connector_type: editOrgForm.connector_type,
        connector_config: editOrgForm.connector_type === 'internal' ? {} : editOrgForm.connector_config,
      };
      await api.put(`/admin/organizations/${editingOrg}`, payload);
      setSuccess('Organization updated successfully');
      setEditingOrg(null);
      setEditOrgForm({ name: '', industry: '', connector_type: 'internal', connector_config: {} });
      loadDashboard();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to update organization');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateUser = async (e) => {
    e.preventDefault();
    if (!editingUser) return;

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      await api.put(`/admin/users/${editingUser}`, editUserForm);
      setSuccess('User updated successfully');
      setEditingUser(null);
      setEditUserForm({ email: '', role: 'user', org_id: '' });
      loadDashboard();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to update user');
    } finally {
      setLoading(false);
    }
  };

  const startEditOrganization = (org) => {
    setEditingOrg(org.id);
    setEditOrgForm({
      name: org.name,
      industry: org.industry || '',
      connector_type: org.connector_type,
      connector_config: org.connector_config || {},
    });
    setActiveTab('edit-org');
  };

  const startEditUser = (user) => {
    setEditingUser(user.id);
    setEditUserForm({
      email: user.email,
      role: user.role,
      org_id: user.org_id || '',
    });
    setActiveTab('edit-user');
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const response = await api.post('/admin/users', newUserForm);
      setSuccess(`User "${response.data.user.email}" created successfully`);
      setNewUserForm({ email: '', password: '', org_id: '', role: 'user' });
      loadDashboard();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to create user');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateUserOrganization = async (userId, orgId) => {
    setError('');
    setSuccess('');

    try {
      const response = await api.put(
        `/admin/users/${userId}`,
        { org_id: orgId || null }
      );
      setSuccess(`User updated successfully`);
      loadDashboard();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to update user');
    }
  };

  const handleDeleteUser = async (userId, email) => {
    if (!confirm(`Are you sure you want to delete ${email}?`)) return;

    setError('');
    setSuccess('');

    try {
      const response = await api.delete(`/admin/users/${userId}`);
      setSuccess(`User deleted successfully`);
      loadDashboard();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete user');
    }
  };

  const handleDeleteOrganization = async (orgId, orgName) => {
    if (!confirm(`Are you sure you want to delete "${orgName}"? This will also delete all users in this organization.`)) return;

    setError('');
    setSuccess('');

    try {
      const response = await api.delete(`/admin/organizations/${orgId}`);
      setSuccess(`Organization deleted successfully`);
      loadDashboard();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete organization');
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (!resetPasswordUser) return;

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      await api.put(`/admin/users/${resetPasswordUser.id}/reset-password`, {
        password: newPassword,
      });
      setSuccess(`Password reset successfully for ${resetPasswordUser.email}`);
      setResetPasswordUser(null);
      setNewPassword('');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to reset password');
    } finally {
      setLoading(false);
    }
  };

  const cancelResetPassword = () => {
    setResetPasswordUser(null);
    setNewPassword('');
    setError('');
  };

  // Filter users by organization
  const filteredUsers = orgFilter
    ? users.filter((u) => u.org_id === orgFilter)
    : users;

  return (
    <div className="admin-container">
      <div className="admin-header">
        <h1>Lia Administration Panel</h1>
        <div className="admin-user-info">
          <span>Logged in as: <strong>{user.email}</strong> ({user.role})</span>
          <button onClick={onLogout} className="logout-btn">Logout</button>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <div className="admin-tabs">
        <button
          className={`tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={`tab-btn ${activeTab === 'create-org' ? 'active' : ''}`}
          onClick={() => setActiveTab('create-org')}
        >
          Create Organization
        </button>
        <button
          className={`tab-btn ${activeTab === 'create-user' ? 'active' : ''}`}
          onClick={() => setActiveTab('create-user')}
        >
          Create User
        </button>
        <button
          className={`tab-btn ${activeTab === 'manage-users' ? 'active' : ''}`}
          onClick={() => setActiveTab('manage-users')}
        >
          Manage Users
        </button>
        <button
          className={`tab-btn ${activeTab === 'organizations' ? 'active' : ''}`}
          onClick={() => setActiveTab('organizations')}
        >
          Organizations
        </button>
        {editingOrg && (
          <button
            className={`tab-btn ${activeTab === 'edit-org' ? 'active' : ''}`}
            onClick={() => setActiveTab('edit-org')}
          >
            Edit Organization
          </button>
        )}
        {editingUser && (
          <button
            className={`tab-btn ${activeTab === 'edit-user' ? 'active' : ''}`}
            onClick={() => setActiveTab('edit-user')}
          >
            Edit User
          </button>
        )}
      </div>

      <div className="admin-content">
        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <div className="tab-content">
            <h2>Dashboard</h2>
            {loading ? (
              <p>Loading...</p>
            ) : (
              <>
                <div className="stats-grid">
                  <div className="stat-card">
                    <h3>Total Organizations</h3>
                    <p className="stat-number">{organizations.length}</p>
                  </div>
                  <div className="stat-card">
                    <h3>Total Users</h3>
                    <p className="stat-number">{users.length}</p>
                  </div>
                </div>

                <h3>Recent Organizations</h3>
                <div className="table-responsive">
                  <table>
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Industry</th>
                        <th>Connector</th>
                        <th>Users</th>
                      </tr>
                    </thead>
                    <tbody>
                      {organizations.slice(0, 5).map((org) => (
                        <tr key={org.id}>
                          <td>{org.name}</td>
                          <td>{org.industry || 'N/A'}</td>
                          <td>{org.connector_type}</td>
                          <td>{org.user_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <h3>Recent Users</h3>
                <div className="table-responsive">
                  <table>
                    <thead>
                      <tr>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Organization</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.slice(0, 5).map((user) => (
                        <tr key={user.id}>
                          <td>{user.email}</td>
                          <td>
                            <span className={`badge badge-${user.role}`}>{user.role}</span>
                          </td>
                          <td>{user.org_name || 'Unassigned'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}

        {/* Create Organization Tab */}
        {activeTab === 'create-org' && (
          <div className="tab-content">
            <h2>Create New Organization</h2>
            <form onSubmit={handleCreateOrganization} className="form">
              <div className="form-group">
                <label htmlFor="org_name">Organization Name *</label>
                <input
                  type="text"
                  id="org_name"
                  placeholder="e.g., Acme Corporation"
                  value={newOrgForm.name}
                  onChange={(e) => setNewOrgForm({ ...newOrgForm, name: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="org_industry">Industry</label>
                <input
                  type="text"
                  id="org_industry"
                  placeholder="e.g., Technology, Finance"
                  value={newOrgForm.industry}
                  onChange={(e) => setNewOrgForm({ ...newOrgForm, industry: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="org_connector">Connector Type *</label>
                <select
                  id="org_connector"
                  value={newOrgForm.connector_type}
                  onChange={(e) =>
                    setNewOrgForm({
                      ...newOrgForm,
                      connector_type: e.target.value,
                      connector_config: {},
                    })
                  }
                >
                  <option value="internal">Internal</option>
                  <option value="salesforce">Salesforce</option>
                  <option value="hubspot">HubSpot</option>
                  <option value="dynamics">Dynamics 365</option>
                  <option value="mysql">MySQL</option>
                  <option value="postgresql">PostgreSQL</option>
                </select>
              </div>

              <ConnectorConfigForm
                connectorType={newOrgForm.connector_type}
                config={newOrgForm.connector_config}
                onChange={(config) => setNewOrgForm({ ...newOrgForm, connector_config: config })}
              />

              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? 'Creating...' : 'Create Organization'}
              </button>
            </form>
          </div>
        )}

        {/* Create User Tab */}
        {activeTab === 'create-user' && (
          <div className="tab-content">
            <h2>Create New User</h2>
            <form onSubmit={handleCreateUser} className="form">
              <div className="form-group">
                <label htmlFor="user_email">Email *</label>
                <input
                  type="email"
                  id="user_email"
                  placeholder="user@example.com"
                  value={newUserForm.email}
                  onChange={(e) => setNewUserForm({ ...newUserForm, email: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="user_password">Password *</label>
                <input
                  type="password"
                  id="user_password"
                  placeholder="••••••••"
                  value={newUserForm.password}
                  onChange={(e) => setNewUserForm({ ...newUserForm, password: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="user_org">Organization *</label>
                <select
                  id="user_org"
                  value={newUserForm.org_id}
                  onChange={(e) => setNewUserForm({ ...newUserForm, org_id: e.target.value })}
                  required
                >
                  <option value="">-- Select Organization --</option>
                  {organizations.map((org) => (
                    <option key={org.id} value={org.id}>
                      {org.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="user_role">Role *</label>
                <select
                  id="user_role"
                  value={newUserForm.role}
                  onChange={(e) => setNewUserForm({ ...newUserForm, role: e.target.value })}
                >
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                  <option value="owner">Owner</option>
                </select>
              </div>

              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? 'Creating...' : 'Create User'}
              </button>
            </form>
          </div>
        )}

        {/* Manage Users Tab */}
        {activeTab === 'manage-users' && (
          <div className="tab-content">
            <h2>Manage Users</h2>

            {/* Organization Filter */}
            <div className="filter-section">
              <label htmlFor="org-filter">Filter by Organization:</label>
              <select
                id="org-filter"
                value={orgFilter}
                onChange={(e) => setOrgFilter(e.target.value)}
                className="org-filter-select"
              >
                <option value="">All Organizations</option>
                {organizations.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name}
                  </option>
                ))}
              </select>
              {orgFilter && (
                <button
                  onClick={() => setOrgFilter('')}
                  className="btn btn-secondary btn-sm"
                  style={{ marginLeft: '10px' }}
                >
                  Clear Filter
                </button>
              )}
            </div>

            {loading ? (
              <p>Loading...</p>
            ) : (
              <div className="table-responsive">
                <table>
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Organization</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map((user) => (
                      <tr key={user.id}>
                        <td>{user.email}</td>
                        <td>
                          <span className={`badge badge-${user.role}`}>{user.role}</span>
                        </td>
                        <td>{user.org_name || 'Unassigned'}</td>
                        <td>
                          <button
                            onClick={() => startEditUser(user)}
                            className="btn btn-primary btn-sm"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => setResetPasswordUser(user)}
                            className="btn btn-warning btn-sm"
                          >
                            Reset Password
                          </button>
                          <button
                            onClick={() => handleDeleteUser(user.id, user.email)}
                            className="btn btn-danger btn-sm"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filteredUsers.length === 0 && (
                  <p style={{ textAlign: 'center', marginTop: '20px' }}>
                    No users found{orgFilter ? ' for the selected organization' : ''}.
                  </p>
                )}
              </div>
            )}

            {/* Password Reset Modal */}
            {resetPasswordUser && (
              <div className="modal-overlay" onClick={cancelResetPassword}>
                <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                  <h3>Reset Password for {resetPasswordUser.email}</h3>
                  <form onSubmit={handleResetPassword}>
                    <div className="form-group">
                      <label htmlFor="new-password">New Password *</label>
                      <input
                        type="password"
                        id="new-password"
                        placeholder="Enter new password (min 6 characters)"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        minLength={6}
                        required
                        autoFocus
                      />
                    </div>
                    <div className="form-actions">
                      <button type="submit" className="btn btn-primary" disabled={loading}>
                        {loading ? 'Resetting...' : 'Reset Password'}
                      </button>
                      <button
                        type="button"
                        onClick={cancelResetPassword}
                        className="btn btn-secondary"
                        disabled={loading}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Organizations Tab */}
        {activeTab === 'organizations' && (
          <div className="tab-content">
            <h2>All Organizations</h2>
            {loading ? (
              <p>Loading...</p>
            ) : (
              <div className="table-responsive">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Industry</th>
                      <th>Connector Type</th>
                      <th>Users</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {organizations.map((org) => (
                      <tr key={org.id}>
                        <td>{org.name}</td>
                        <td>{org.industry || 'N/A'}</td>
                        <td>{org.connector_type}</td>
                        <td>{org.user_count}</td>
                        <td>
                          <button
                            onClick={() => startEditOrganization(org)}
                            className="btn btn-primary btn-sm"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteOrganization(org.id, org.name)}
                            className="btn btn-danger btn-sm"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Edit Organization Tab */}
        {activeTab === 'edit-org' && editingOrg && (
          <div className="tab-content">
            <h2>Edit Organization</h2>
            <form onSubmit={handleUpdateOrganization} className="form">
              <div className="form-group">
                <label htmlFor="edit_org_name">Organization Name *</label>
                <input
                  type="text"
                  id="edit_org_name"
                  placeholder="e.g., Acme Corporation"
                  value={editOrgForm.name}
                  onChange={(e) => setEditOrgForm({ ...editOrgForm, name: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="edit_org_industry">Industry</label>
                <input
                  type="text"
                  id="edit_org_industry"
                  placeholder="e.g., Technology, Finance"
                  value={editOrgForm.industry}
                  onChange={(e) => setEditOrgForm({ ...editOrgForm, industry: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="edit_org_connector">Connector Type *</label>
                <select
                  id="edit_org_connector"
                  value={editOrgForm.connector_type}
                  onChange={(e) =>
                    setEditOrgForm({
                      ...editOrgForm,
                      connector_type: e.target.value,
                      connector_config: {},
                    })
                  }
                >
                  <option value="internal">Internal</option>
                  <option value="salesforce">Salesforce</option>
                  <option value="hubspot">HubSpot</option>
                  <option value="dynamics">Dynamics 365</option>
                  <option value="mysql">MySQL</option>
                  <option value="postgresql">PostgreSQL</option>
                </select>
              </div>

              <ConnectorConfigForm
                connectorType={editOrgForm.connector_type}
                config={editOrgForm.connector_config}
                onChange={(config) => setEditOrgForm({ ...editOrgForm, connector_config: config })}
              />

              <div className="form-actions">
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? 'Saving...' : 'Save Organization'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setEditingOrg(null);
                    setActiveTab('organizations');
                  }}
                  className="btn btn-secondary"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Edit User Tab */}
        {activeTab === 'edit-user' && editingUser && (
          <div className="tab-content">
            <h2>Edit User</h2>
            <form onSubmit={handleUpdateUser} className="form">
              <div className="form-group">
                <label htmlFor="edit_user_email">Email *</label>
                <input
                  type="email"
                  id="edit_user_email"
                  placeholder="user@example.com"
                  value={editUserForm.email}
                  onChange={(e) => setEditUserForm({ ...editUserForm, email: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="edit_user_role">Role *</label>
                <select
                  id="edit_user_role"
                  value={editUserForm.role}
                  onChange={(e) => setEditUserForm({ ...editUserForm, role: e.target.value })}
                >
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                  <option value="owner">Owner</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="edit_user_org">Organization</label>
                <select
                  id="edit_user_org"
                  value={editUserForm.org_id}
                  onChange={(e) => setEditUserForm({ ...editUserForm, org_id: e.target.value })}
                >
                  <option value="">-- Unassigned --</option>
                  {organizations.map((org) => (
                    <option key={org.id} value={org.id}>
                      {org.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-actions">
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? 'Saving...' : 'Save User'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setEditingUser(null);
                    setActiveTab('manage-users');
                  }}
                  className="btn btn-secondary"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
