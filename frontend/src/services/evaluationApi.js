import client from "../api/client";

export const evaluationApi = {
  getBenchmark: () => client.get("/evaluation/benchmark"),
};
