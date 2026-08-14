export default function FormInput({ label, error, ...inputProps }) {
  return (
    <div className="mb-3">
      {label && <label className="form-label">{label}</label>}
      <input className={`form-control ${error ? "is-invalid" : ""}`} {...inputProps} />
      {error && <div className="invalid-feedback">{error}</div>}
    </div>
  );
}
