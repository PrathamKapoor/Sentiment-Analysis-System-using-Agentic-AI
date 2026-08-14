import client from "../api/client";

export const alertApi = {
  list: (projectId, params) => client.get(`/projects/${projectId}/alerts`, { params }),
  create: (projectId, payload) => client.post(`/projects/${projectId}/alerts`, payload),
  evaluateProject: (projectId) => client.post(`/projects/${projectId}/alerts/evaluate`),
  get: (alertId) => client.get(`/alerts/${alertId}`),
  update: (alertId, payload) => client.patch(`/alerts/${alertId}`, payload),
  remove: (alertId) => client.delete(`/alerts/${alertId}`),
  enable: (alertId) => client.post(`/alerts/${alertId}/enable`),
  disable: (alertId) => client.post(`/alerts/${alertId}/disable`),
  evaluate: (alertId) => client.post(`/alerts/${alertId}/evaluate`),
  acknowledge: (alertId) => client.post(`/alerts/${alertId}/acknowledge`),
  assign: (alertId, userId) => client.post(`/alerts/${alertId}/assign`, { userId }),
  resolve: (alertId, resolutionNotes) => client.post(`/alerts/${alertId}/resolve`, { resolutionNotes }),
};
