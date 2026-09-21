import client from "../api/client";

// Project website context (optional business-context URL on a project,
// plus a cached bounded single-page extraction).
export const websiteApi = {
  getContext: (projectId) => client.get(`/projects/${projectId}/website/context`),
  setContext: (projectId, payload) =>
    client.put(`/projects/${projectId}/website/context`, payload),
  refreshContext: (projectId) =>
    client.post(`/projects/${projectId}/website/context/refresh`),
};
