import PropTypes from 'prop-types';
import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    // Log only the message: never dump component props, tokens or user data.
    console.error('Unexpected UI error:', error?.message);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <main className="auth-page">
        <div className="card card-narrow" role="alert">
          <h1 className="brand">Lia</h1>
          <h2 className="card-subtitle">Something went wrong</h2>
          <p className="text-secondary">
            An unexpected error occurred. Reload the page to try again.
          </p>
          <button type="button" className="btn btn-primary btn-block" onClick={() => window.location.reload()}>
            Reload page
          </button>
        </div>
      </main>
    );
  }
}

ErrorBoundary.propTypes = { children: PropTypes.node };
