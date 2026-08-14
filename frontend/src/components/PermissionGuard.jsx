import { useAuth } from "../contexts/AuthContext";

/** Conditionally renders children only if the active org membership has the permission. */
export default function PermissionGuard({ permission, children, fallback = null }) {
  const { hasPermission } = useAuth();
  return hasPermission(permission) ? children : fallback;
}
