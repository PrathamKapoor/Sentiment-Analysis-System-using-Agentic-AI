import client from "../api/client";

export const organisationApi = {
  get: (organisationId) => client.get(`/organisations/${organisationId}`),
  update: (organisationId, payload) => client.patch(`/organisations/${organisationId}`, payload),
  listUsers: (organisationId) => client.get(`/organisations/${organisationId}/users`),
  inviteUser: (organisationId, payload) =>
    client.post(`/organisations/${organisationId}/users/invite`, payload),
  updateUser: (organisationId, userId, payload) =>
    client.patch(`/organisations/${organisationId}/users/${userId}`, payload),
  removeUser: (organisationId, userId) =>
    client.delete(`/organisations/${organisationId}/users/${userId}`),
  listRoles: (organisationId) => client.get(`/organisations/${organisationId}/roles`),
  createRole: (organisationId, payload) =>
    client.post(`/organisations/${organisationId}/roles`, payload),
  updateRole: (organisationId, roleId, payload) =>
    client.patch(`/organisations/${organisationId}/roles/${roleId}`, payload),
  deleteRole: (organisationId, roleId) =>
    client.delete(`/organisations/${organisationId}/roles/${roleId}`),
  assignRole: (organisationId, roleId, userId) =>
    client.post(`/organisations/${organisationId}/roles/${roleId}/assign`, { userId }),
  unassignRole: (organisationId, roleId, userId) =>
    client.post(`/organisations/${organisationId}/roles/${roleId}/unassign`, { userId }),
};
