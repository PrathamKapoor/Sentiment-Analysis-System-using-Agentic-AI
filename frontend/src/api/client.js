import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000/api/v1";

const client = axios.create({ baseURL: BASE_URL });

function getAccessToken() {
  return localStorage.getItem("accessToken");
}

function getRefreshToken() {
  return localStorage.getItem("refreshToken");
}

export function setTokens({ accessToken, refreshToken }) {
  if (accessToken) localStorage.setItem("accessToken", accessToken);
  if (refreshToken) localStorage.setItem("refreshToken", refreshToken);
}

export function clearTokens() {
  localStorage.removeItem("accessToken");
  localStorage.removeItem("refreshToken");
}

export function setActiveOrganisationId(organisationId) {
  if (organisationId) localStorage.setItem("activeOrganisationId", organisationId);
}

export function getActiveOrganisationId() {
  return localStorage.getItem("activeOrganisationId");
}

client.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const orgId = getActiveOrganisationId();
  if (orgId) config.headers["X-Organisation-Id"] = orgId;
  return config;
});

let refreshPromise = null;

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;
    const code = error.response?.data?.error?.code;

    if (status === 401 && code === "UNAUTHENTICATED" && !original._retry) {
      original._retry = true;
      const refreshToken = getRefreshToken();
      if (!refreshToken) {
        clearTokens();
        window.location.href = "/login";
        return Promise.reject(error);
      }
      try {
        if (!refreshPromise) {
          refreshPromise = axios
            .post(`${BASE_URL}/auth/refresh`, {}, {
              headers: { Authorization: `Bearer ${refreshToken}` },
            })
            .finally(() => {
              refreshPromise = null;
            });
        }
        const refreshResp = await refreshPromise;
        setTokens(refreshResp.data.data);
        original.headers.Authorization = `Bearer ${refreshResp.data.data.accessToken}`;
        return client(original);
      } catch (refreshError) {
        clearTokens();
        window.location.href = "/login";
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);

export default client;
