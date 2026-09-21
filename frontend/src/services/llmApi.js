import client from "../api/client";

// Public LLM provider status. Safe for any authenticated user; the
// server returns no secrets, no API key material, no full base URL.
export const llmApi = {
  status: () => client.get("/llm/status"),
};
