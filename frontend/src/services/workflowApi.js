import client from "../api/client";

export const workflowApi = {
  list: (projectId) => client.get(`/projects/${projectId}/workflows`),
  start: (projectId, payload) => client.post(`/projects/${projectId}/workflows`, payload),
  get: (workflowId) => client.get(`/workflows/${workflowId}`),
  steps: (workflowId) => client.get(`/workflows/${workflowId}/steps`),
  cancel: (workflowId) => client.post(`/workflows/${workflowId}/cancel`),
  resume: (workflowId) => client.post(`/workflows/${workflowId}/resume`),
  approve: (workflowId) => client.post(`/workflows/${workflowId}/approve`),
  reject: (workflowId, reason) => client.post(`/workflows/${workflowId}/reject`, { reason }),
};
