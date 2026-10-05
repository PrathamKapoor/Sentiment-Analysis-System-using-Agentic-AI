import client from "../api/client";

export const securityFindingApi = {
  list: (projectId) => client.get(`/projects/${projectId}/security-findings`),
  analyze: (projectId) => client.post(`/projects/${projectId}/security-findings/analyze`),
  review: (projectId, findingId, payload) => client.patch(
    `/projects/${projectId}/security-findings/${findingId}`, payload,
  ),
};
