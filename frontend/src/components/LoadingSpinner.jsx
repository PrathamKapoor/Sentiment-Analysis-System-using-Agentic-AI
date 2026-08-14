export default function LoadingSpinner({ label = "Loading..." }) {
  return (
    <div className="d-flex align-items-center justify-content-center py-5">
      <div className="spinner-border text-primary me-2" role="status" />
      <span>{label}</span>
    </div>
  );
}
