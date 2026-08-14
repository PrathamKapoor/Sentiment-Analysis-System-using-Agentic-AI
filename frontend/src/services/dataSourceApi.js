import client from "../api/client";

export const dataSourceApi = {
  list: (projectId) => client.get(`/projects/${projectId}/sources`),
  create: (projectId, payload) => client.post(`/projects/${projectId}/sources`, payload),
  update: (sourceId, payload) => client.patch(`/sources/${sourceId}`, payload),
  remove: (sourceId) => client.delete(`/sources/${sourceId}`),
  testConnection: (sourceId) => client.post(`/sources/${sourceId}/test-connection`),
  preview: (sourceId, payload) => client.post(`/sources/${sourceId}/preview`, payload || {}),
  collect: (sourceId, payload) => client.post(`/sources/${sourceId}/collect`, payload || {}),
  collectionStatus: (sourceId) => client.get(`/sources/${sourceId}/collection-status`),
  collectionHistory: (sourceId) => client.get(`/sources/${sourceId}/collection-history`),
  collectEnabled: (projectId) => client.post(`/projects/${projectId}/sources/collect-enabled`),
};
