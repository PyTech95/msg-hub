import axios from "axios";

// Empty/unset REACT_APP_BACKEND_URL → same-origin relative "/api" (production VPS)
const BASE = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
export const API = `${BASE}/api`;

const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("cpaas_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && window.location.pathname !== "/login") {
      localStorage.removeItem("cpaas_token");
      localStorage.removeItem("cpaas_user");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;
