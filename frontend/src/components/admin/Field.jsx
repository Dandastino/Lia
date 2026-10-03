import PropTypes from 'prop-types';
// Label + control + inline error, wired together with htmlFor / aria-describedby.
// `as` is 'input' (default) or 'select' (children are the options).
export default function Field({ id, label, required = false, error, as = 'input', children, ...controlProps }) {
  const Control = as;
  return (
    <div className="form-group">
      <label htmlFor={id} className={required ? 'is-required' : undefined}>
        {label}
      </label>
      <Control
        id={id}
        aria-required={required ? 'true' : undefined}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        {...controlProps}
      >
        {children}
      </Control>
      {error && <p id={`${id}-error`} className="field-error">{error}</p>}
    </div>
  );
}

Field.propTypes = { id: PropTypes.string.isRequired, label: PropTypes.string.isRequired, required: PropTypes.bool, error: PropTypes.string, as: PropTypes.string, children: PropTypes.node };
