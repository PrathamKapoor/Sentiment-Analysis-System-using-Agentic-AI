import client from "../api/client";

export const authApi = {
  register: (payload) => client.post("/auth/register", payload),
  login: (payload) => client.post("/auth/login", payload),
  logout: () => client.post("/auth/logout"),
  me: () => client.get("/auth/me"),
};
