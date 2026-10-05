import client from "../api/client";

export const investigationApi = {
  list: (projectId) => client.get(`/projects/${projectId}/investigations`),
  create: (projectId, payload) => client.post(`/projects/${projectId}/investigations`, payload),
  get: (projectId, investigationId) => client.get(`/projects/${projectId}/investigations/${investigationId}`),
  cancel: (projectId, investigationId) => client.post(`/projects/${projectId}/investigations/${investigationId}/cancel`),
  reviewFinding: (projectId, investigationId, findingId, payload) =>
    client.patch(`/projects/${projectId}/investigations/${investigationId}/findings/${findingId}`, payload),
};
