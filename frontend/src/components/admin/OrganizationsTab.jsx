import PropTypes from 'prop-types';
import { EmptyState, LoadingState } from './DataState';

export default function OrganizationsTab({ organizations, loading, onEdit, onDelete }) {
  if (loading) return <LoadingState label="Loading organizations..." />;
  if (organizations.length === 0) return <EmptyState>No organizations yet.</EmptyState>;

  return (
    <div className="table-responsive">
      <table aria-label="Organizations">
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Industry</th>
            <th scope="col">Connector type</th>
            <th scope="col">Users</th>
            <th scope="col">Actions</th>
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
                <div className="row-actions">
                  <button type="button" onClick={() => onEdit(org)} className="btn btn-primary btn-sm" aria-label={`Edit ${org.name}`}>
                    Edit
                  </button>
                  <button type="button" onClick={() => onDelete(org)} className="btn btn-danger btn-sm" aria-label={`Delete ${org.name}`}>
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

OrganizationsTab.propTypes = { organizations: PropTypes.arrayOf(PropTypes.shape({ id: PropTypes.string, name: PropTypes.string, industry: PropTypes.string, connector_type: PropTypes.string, user_count: PropTypes.number })).isRequired, loading: PropTypes.bool, onEdit: PropTypes.func.isRequired, onDelete: PropTypes.func.isRequired };
