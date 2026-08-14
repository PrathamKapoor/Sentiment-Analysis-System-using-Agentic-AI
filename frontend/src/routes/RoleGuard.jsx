import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function RoleGuard({ allowedRoles }) {
  const { hasRole } = useAuth();
  const allowed = allowedRoles.some(hasRole);
  if (!allowed) return <Navigate to="/access-denied" replace />;
  return <Outlet />;
}
