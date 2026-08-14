export default function ErrorAlert({ error, onDismiss }) {
  if (!error) return null;
  const message =
    error?.response?.data?.error?.message || error?.message || "Something went wrong";
  const details = error?.response?.data?.error?.details;
  const fieldErrors = details?.errors || details?.fieldErrors;
  return (
    <div className="alert alert-danger d-flex justify-content-between align-items-center" role="alert">
      <span>{message}{Array.isArray(fieldErrors) && fieldErrors.length > 0 && <><br /><small>{fieldErrors.slice(0, 3).map((item) => `Row ${item.row ?? "—"}: ${item.reason}`).join(" · ")}</small></>}</span>
      {onDismiss && (
        <button type="button" className="btn-close" onClick={onDismiss} aria-label="Close" />
      )}
    </div>
  );
}
