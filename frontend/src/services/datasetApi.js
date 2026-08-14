import client from "../api/client";

export const datasetApi = {
  list: (projectId) => client.get(`/projects/${projectId}/datasets`),
  upload: (projectId, file, fileType) => {
    const form = new FormData();
    form.append("file", file);
    form.append("fileType", fileType);
    return client.post(`/projects/${projectId}/datasets`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  get: (datasetId) => client.get(`/datasets/${datasetId}`),
  mapColumns: (datasetId, mapping) => client.post(`/datasets/${datasetId}/map-columns`, mapping),
  validate: (datasetId) => client.post(`/datasets/${datasetId}/validate`),
  process: (datasetId) => client.post(`/datasets/${datasetId}/process`),
  remove: (datasetId) => client.delete(`/datasets/${datasetId}`),
};
