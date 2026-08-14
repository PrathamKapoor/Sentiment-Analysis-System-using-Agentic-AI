import client from "../api/client";

export const reportApi = {
  list: (projectId) => client.get(`/projects/${projectId}/reports`),
  create: (projectId, payload) => client.post(`/projects/${projectId}/reports`, payload),
  get: (reportId) => client.get(`/reports/${reportId}`),
  remove: (reportId) => client.delete(`/reports/${reportId}`),
  download: (reportId) => client.get(`/reports/${reportId}/download`, { responseType: "blob" }),
};

// Authenticated downloads can't just be an <a href> (no way to attach the
// JWT), so fetch as a blob and trigger the save via a throwaway object URL.
export async function downloadReportFile(reportId, filename) {
  const response = await reportApi.download(reportId);
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
