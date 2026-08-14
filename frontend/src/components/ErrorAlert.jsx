export default function ErrorAlert({ error, onDismiss }) {
  if (!error) return null;
  const message =
    error?.response?.data?.error?.message || error?.message || "Something went wrong";
  return (
    <div className="alert alert-danger d-flex justify-content-between align-items-center" role="alert">
      <span>{message}</span>
      {onDismiss && (
        <button type="button" className="btn-close" onClick={onDismiss} aria-label="Close" />
      )}
    </div>
  );
}
