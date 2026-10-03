import PropTypes from 'prop-types';
import { LoadingState } from './DataState';

function UsersTableSummary({ users }) {
  return (
  <div className="table-responsive">
    <table aria-label="Recent users">
      <thead>
        <tr>
          <th scope="col">Email</th>
          <th scope="col">Role</th>
          <th scope="col">Organization</th>
        </tr>
      </thead>
      <tbody>
        {users.map((u) => (
          <tr key={u.id}>
            <td>{u.email}</td>
            <td><span className={`badge badge-${u.role}`}>{u.role}</span></td>
            <td>{u.org_name || 'Unassigned'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
  );
}

UsersTableSummary.propTypes = { users: PropTypes.arrayOf(PropTypes.shape({ id: PropTypes.string, email: PropTypes.string, role: PropTypes.string, org_id: PropTypes.string, org_name: PropTypes.string })).isRequired };

export default function DashboardTab({ organizations, users, loading }) {
  if (loading) return <LoadingState label="Loading dashboard..." />;

  return (
    <>
      <div className="stats-grid">
        <div className="stat-card">
          <h3>Total organizations</h3>
          <p className="stat-number">{organizations.length}</p>
        </div>
        <div className="stat-card">
          <h3>Total users</h3>
          <p className="stat-number">{users.length}</p>
        </div>
      </div>

      <h3>Recent organizations</h3>
      {organizations.length === 0 ? (
        <p className="text-secondary">No organizations yet. Create the first one from the &ldquo;Create organization&rdquo; tab.</p>
      ) : (
        <div className="table-responsive">
          <table aria-label="Recent organizations">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Industry</th>
                <th scope="col">Connector</th>
                <th scope="col">Users</th>
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
      )}

      <h3>Recent users</h3>
      {users.length === 0 ? (
        <p className="text-secondary">No users yet.</p>
      ) : (
        <UsersTableSummary users={users.slice(0, 5)} />
      )}
    </>
  );
}

DashboardTab.propTypes = { organizations: PropTypes.arrayOf(PropTypes.shape({ id: PropTypes.string, name: PropTypes.string, industry: PropTypes.string, connector_type: PropTypes.string, user_count: PropTypes.number })).isRequired, users: PropTypes.arrayOf(PropTypes.shape({ id: PropTypes.string, email: PropTypes.string, role: PropTypes.string, org_id: PropTypes.string, org_name: PropTypes.string })).isRequired, loading: PropTypes.bool };
