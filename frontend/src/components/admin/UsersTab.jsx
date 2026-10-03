import PropTypes from 'prop-types';
import { EmptyState, LoadingState } from './DataState';

export default function UsersTab({ users, organizations, orgFilter, onFilterChange, loading, onEdit, onResetPassword, onDelete }) {
  const filtered = orgFilter ? users.filter((u) => u.org_id === orgFilter) : users;

  return (
    <>
      <div className="filter-section">
        <label htmlFor="org-filter">Filter by organization</label>
        <select id="org-filter" value={orgFilter} onChange={(e) => onFilterChange(e.target.value)}>
          <option value="">All organizations</option>
          {organizations.map((org) => (
            <option key={org.id} value={org.id}>{org.name}</option>
          ))}
        </select>
        {orgFilter && (
          <button type="button" onClick={() => onFilterChange('')} className="btn btn-secondary btn-sm">
            Clear filter
          </button>
        )}
      </div>

      {loading ? (
        <LoadingState label="Loading users..." />
      ) : filtered.length === 0 ? (
        <EmptyState>No users found{orgFilter ? ' for the selected organization' : ''}.</EmptyState>
      ) : (
        <div className="table-responsive">
          <table aria-label="Users">
            <thead>
              <tr>
                <th scope="col">Email</th>
                <th scope="col">Role</th>
                <th scope="col">Organization</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td><span className={`badge badge-${u.role}`}>{u.role}</span></td>
                  <td>{u.org_name || 'Unassigned'}</td>
                  <td>
                    <div className="row-actions">
                      <button type="button" onClick={() => onEdit(u)} className="btn btn-primary btn-sm" aria-label={`Edit ${u.email}`}>
                        Edit
                      </button>
                      <button type="button" onClick={() => onResetPassword(u)} className="btn btn-warning btn-sm" aria-label={`Reset password for ${u.email}`}>
                        Reset password
                      </button>
                      <button type="button" onClick={() => onDelete(u)} className="btn btn-danger btn-sm" aria-label={`Delete ${u.email}`}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

UsersTab.propTypes = { users: PropTypes.arrayOf(PropTypes.shape({ id: PropTypes.string, email: PropTypes.string, role: PropTypes.string, org_id: PropTypes.string, org_name: PropTypes.string })).isRequired, organizations: PropTypes.arrayOf(PropTypes.shape({ id: PropTypes.string, name: PropTypes.string, industry: PropTypes.string, connector_type: PropTypes.string, user_count: PropTypes.number })).isRequired, orgFilter: PropTypes.string.isRequired, onFilterChange: PropTypes.func.isRequired, loading: PropTypes.bool, onEdit: PropTypes.func.isRequired, onResetPassword: PropTypes.func.isRequired, onDelete: PropTypes.func.isRequired };
