import client from "../api/client";

export const recommendationApi = {
  generate: (projectId, payload = {}) => client.post(`/projects/${projectId}/recommendations/generate`, payload),
  list: (projectId, params) => client.get(`/projects/${projectId}/recommendations`, { params }),
  get: (recommendationId) => client.get(`/recommendations/${recommendationId}`),
  update: (recommendationId, payload) => client.patch(`/recommendations/${recommendationId}`, payload),
  assign: (recommendationId, userId) => client.post(`/recommendations/${recommendationId}/assign`, { userId }),
  accept: (recommendationId) => client.post(`/recommendations/${recommendationId}/accept`),
  reject: (recommendationId) => client.post(`/recommendations/${recommendationId}/reject`),
  complete: (recommendationId) => client.post(`/recommendations/${recommendationId}/complete`),
};
