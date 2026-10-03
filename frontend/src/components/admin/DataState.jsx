import PropTypes from 'prop-types';

export function LoadingState({ label = 'Loading...' }) {
  return (
    <div className="state-box" role="status">
      <div className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function EmptyState({ children }) {
  return (
    <div className="state-box">
      <p>{children}</p>
    </div>
  );
}

LoadingState.propTypes = { label: PropTypes.string };
EmptyState.propTypes = { children: PropTypes.node };
