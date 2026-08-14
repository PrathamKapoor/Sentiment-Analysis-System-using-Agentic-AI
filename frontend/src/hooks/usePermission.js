import { useAuth } from "../contexts/AuthContext";

export function usePermission(code) {
  const { hasPermission } = useAuth();
  return hasPermission(code);
}
