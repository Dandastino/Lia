import PropTypes from 'prop-types';
import Modal from './Modal';

// Confirmation for destructive actions. Focus starts on "Cancel" (the safe choice).
export default function ConfirmDialog({ title, message, confirmLabel = 'Delete', busy = false, onConfirm, onCancel }) {
  return (
    <Modal role="alertdialog" labelledBy="confirm-title" describedBy="confirm-message" onClose={busy ? undefined : onCancel}>
      <h2 id="confirm-title">{title}</h2>
      <p id="confirm-message">{message}</p>
      <div className="form-actions">
        <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={busy}>
          {busy ? 'Deleting...' : confirmLabel}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy} data-autofocus>
          Cancel
        </button>
      </div>
    </Modal>
  );
}

ConfirmDialog.propTypes = { title: PropTypes.string.isRequired, message: PropTypes.string.isRequired, confirmLabel: PropTypes.string, busy: PropTypes.bool, onConfirm: PropTypes.func.isRequired, onCancel: PropTypes.func.isRequired };
