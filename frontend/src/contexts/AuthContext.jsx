import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { authApi } from "../services/authApi";
import {
  setTokens, clearTokens, setActiveOrganisationId, getActiveOrganisationId,
} from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [organisations, setOrganisations] = useState([]);
  const [activeOrganisation, setActiveOrganisation] = useState(null);
  const [permissions, setPermissions] = useState([]);
  const [loading, setLoading] = useState(true);

  const applyLoginResult = useCallback((data) => {
    setTokens(data);
    setUser(data.user);
    setOrganisations(data.organisations || []);
    setActiveOrganisation(data.activeOrganisation || null);
    setPermissions(data.permissions || []);
    if (data.activeOrganisation) {
      setActiveOrganisationId(data.activeOrganisation.organisationId);
    }
  }, []);

  const loadCurrentUser = useCallback(async () => {
    try {
      const resp = await authApi.me();
      setUser(resp.data.data.user);
      setOrganisations(resp.data.data.organisations || []);
      const orgId = getActiveOrganisationId();
      const active =
        resp.data.data.activeOrganisation ||
        resp.data.data.organisations.find((o) => o.organisationId === orgId) ||
        resp.data.data.organisations[0] ||
        null;
      setActiveOrganisation(active);
      setPermissions(resp.data.data.permissions || []);
    } catch {
      clearTokens();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("accessToken");
    if (token) {
      loadCurrentUser();
    } else {
      setLoading(false);
    }
  }, [loadCurrentUser]);

  const login = async (email, password) => {
    const resp = await authApi.login({ email, password });
    applyLoginResult(resp.data.data);
    return resp.data.data;
  };

  const register = async (payload) => {
    const resp = await authApi.register(payload);
    // Registration doesn't return permissions/org list directly — log in right after.
    setTokens(resp.data.data);
    const loginResp = await authApi.login({ email: payload.email, password: payload.password });
    applyLoginResult(loginResp.data.data);
    return loginResp.data.data;
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } finally {
      clearTokens();
      setUser(null);
      setOrganisations([]);
      setActiveOrganisation(null);
      setPermissions([]);
    }
  };

  const switchOrganisation = async (organisationId) => {
    setActiveOrganisationId(organisationId);
    const org = organisations.find((o) => o.organisationId === organisationId);
    setActiveOrganisation(org || null);
    setPermissions([]);
    try {
      const resp = await authApi.me();
      setActiveOrganisation(resp.data.data.activeOrganisation || org || null);
      setPermissions(resp.data.data.permissions || []);
    } catch {
      // Fail closed; a later successful session refresh restores permissions.
      setPermissions([]);
    }
  };

  const hasRole = (roleName) => (activeOrganisation?.roles || []).includes(roleName);
  const hasPermission = (code) => permissions.includes(code);

  const value = {
    user, organisations, activeOrganisation, permissions, loading,
    login, register, logout, switchOrganisation, hasRole, hasPermission,
    isAuthenticated: !!user,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
