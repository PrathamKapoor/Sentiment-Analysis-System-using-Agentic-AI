import client from "../api/client";

export const reviewApi = {
  list: (projectId, params) => client.get(`/projects/${projectId}/reviews`, { params }),
  get: (reviewId) => client.get(`/reviews/${reviewId}`),
  update: (reviewId, payload) => client.patch(`/reviews/${reviewId}`, payload),
  markSpam: (reviewId, isSpam = true) => client.post(`/reviews/${reviewId}/mark-spam`, { isSpam }),
  getSentiment: (reviewId) => client.get(`/reviews/${reviewId}/sentiment`),
  correctSentiment: (reviewId, label, reason) =>
    client.post(`/reviews/${reviewId}/correct-sentiment`, { label, reason }),
  getAspects: (reviewId) => client.get(`/reviews/${reviewId}/aspects`),
};
