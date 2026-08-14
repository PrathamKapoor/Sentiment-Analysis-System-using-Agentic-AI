import client from "../api/client";

export const projectApi = {
  list: (params) => client.get("/projects", { params }),
  create: (payload) => client.post("/projects", payload),
  get: (projectId) => client.get(`/projects/${projectId}`),
  update: (projectId, payload) => client.patch(`/projects/${projectId}`, payload),
  remove: (projectId) => client.delete(`/projects/${projectId}`),
  archive: (projectId, archived = true) =>
    client.post(`/projects/${projectId}/archive`, { archived }),
  listMembers: (projectId) => client.get(`/projects/${projectId}/members`),
  addMember: (projectId, userId) => client.post(`/projects/${projectId}/members`, { userId }),
  removeMember: (projectId, userId) => client.delete(`/projects/${projectId}/members/${userId}`),
};
