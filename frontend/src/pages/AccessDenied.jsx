import { Link } from "react-router-dom";

export default function AccessDenied() {
  return (
    <div className="text-center py-5">
      <h2>Access Denied</h2>
      <p className="text-muted">You don't have permission to view this page.</p>
      <Link to="/dashboard" className="btn btn-primary">Back to Dashboard</Link>
    </div>
  );
}
