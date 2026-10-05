import client from "../api/client";

export const entityApi = {
  get: (projectId) => client.get(`/projects/${projectId}/entity`),
  save: (projectId, payload) => client.put(`/projects/${projectId}/entity`, payload),
  discover: (projectId, description, known = {}) => client.post(`/projects/${projectId}/entity/discover`, {
    description,
    sku: known.sku || null,
    canonicalUrl: known.canonicalUrl || null,
    identifiers: known.identifiers || {},
  }),
};
