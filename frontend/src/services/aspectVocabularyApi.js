import client from "../api/client";

export const aspectVocabularyApi = {
  list: (projectId) => client.get(`/projects/${projectId}/aspect-vocabulary`),
  create: (projectId, data) => client.post(`/projects/${projectId}/aspect-vocabulary`, data),
  update: (projectId, vocabId, data) => client.patch(`/projects/${projectId}/aspect-vocabulary/${vocabId}`, data),
  remove: (projectId, vocabId) => client.delete(`/projects/${projectId}/aspect-vocabulary/${vocabId}`),
};
