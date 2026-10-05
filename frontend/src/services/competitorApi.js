import client from "../api/client";

export const competitorApi = {
  get: (projectId) => client.get(`/projects/${projectId}/analysis/competitors`),
};
