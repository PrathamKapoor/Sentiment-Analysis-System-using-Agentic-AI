import client from "../api/client";

export const analysisApi = {
  runSentiment: (projectId, payload = {}) => client.post(`/projects/${projectId}/analysis/sentiment`, payload),
  reanalyseSentiment: (projectId, payload = {}) =>
    client.post(`/projects/${projectId}/analysis/sentiment/reanalyse`, payload),
  getSentimentResults: (projectId, params) => client.get(`/projects/${projectId}/analysis/sentiment`, { params }),
  getSentimentSummary: (projectId, params) =>
    client.get(`/projects/${projectId}/analysis/sentiment/summary`, { params }),

  runTopics: (projectId, payload = {}) => client.post(`/projects/${projectId}/analysis/topics`, payload),
  listTopics: (projectId) => client.get(`/projects/${projectId}/analysis/topics`),
  getTopic: (projectId, topicId) => client.get(`/projects/${projectId}/analysis/topics/${topicId}`),
  getTopicReviews: (projectId, topicId) => client.get(`/projects/${projectId}/analysis/topics/${topicId}/reviews`),

  getKeywords: (projectId, params) => client.get(`/projects/${projectId}/analysis/keywords`, { params }),
  getWordCloud: (projectId, params) => client.get(`/projects/${projectId}/analysis/word-cloud`, { params }),

  getTrends: (projectId, params) => client.get(`/projects/${projectId}/analysis/trends`, { params }),

  runAspects: (projectId, payload = {}) => client.post(`/projects/${projectId}/analysis/aspects`, payload),
  reanalyseAspects: (projectId, payload = {}) => client.post(`/projects/${projectId}/analysis/aspects/reanalyse`, payload),
  listAspects: (projectId, params) => client.get(`/projects/${projectId}/analysis/aspects`, { params }),
  getAspect: (projectId, aspectId, params) => client.get(`/projects/${projectId}/analysis/aspects/${aspectId}`, { params }),
  getAspectReviews: (projectId, aspectId, params) =>
    client.get(`/projects/${projectId}/analysis/aspects/${aspectId}/reviews`, { params }),

  compareProjects: (projectId, payload) => client.post(`/projects/${projectId}/analysis/comparison`, payload),
};
