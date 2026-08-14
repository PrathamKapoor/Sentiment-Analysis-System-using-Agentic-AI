import client from "../api/client";

export const aiSummaryApi = {
  generate: (projectId, payload) => client.post(`/projects/${projectId}/ai-summaries`, payload),
  regenerate: (projectId, payload) => client.post(`/projects/${projectId}/ai-summaries/regenerate`, payload),
  list: (projectId) => client.get(`/projects/${projectId}/ai-summaries`),
  get: (summaryId) => client.get(`/ai-summaries/${summaryId}`),
  update: (summaryId, sections) => client.patch(`/ai-summaries/${summaryId}`, { sections }),
  submitForReview: (summaryId) => client.post(`/ai-summaries/${summaryId}/submit-for-review`),
  approve: (summaryId, editedContent) => client.post(`/ai-summaries/${summaryId}/approve`, { editedContent }),
  reject: (summaryId, reason) => client.post(`/ai-summaries/${summaryId}/reject`, { reason }),
};
