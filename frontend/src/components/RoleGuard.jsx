import { useAuth } from "../contexts/AuthContext";

/** Inline (non-route) role gate — conditionally renders children based on role. */
export default function RoleGuard({ exclude, children, fallback = null }) {
  const { hasRole } = useAuth();
  const blocked = (exclude || []).some(hasRole);
  return blocked ? fallback : children;
}
