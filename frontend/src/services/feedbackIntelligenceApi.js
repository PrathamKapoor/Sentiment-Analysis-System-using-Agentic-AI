import client from "../api/client";

export const feedbackIntelligenceApi = {
  categories: (projectId) => client.get(`/projects/${projectId}/analysis/feedback-categories`),
};
