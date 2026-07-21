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

// Auto-refresh on 401 — single-flight (all concurrent requests wait on the same refresh call)
let refreshPromise = null;
async function tryRefresh() {
  if (refreshPromise) return refreshPromise;
  const rt = localStorage.getItem("cpaas_refresh_token");
  if (!rt) return null;
  refreshPromise = axios.post(`${API}/auth/refresh`, { refresh_token: rt }, { withCredentials: true })
    .then(r => {
      localStorage.setItem("cpaas_token", r.data.token);
      if (r.data.refresh_token) localStorage.setItem("cpaas_refresh_token", r.data.refresh_token);
      return r.data.token;
    })
    .catch(() => null)
    .finally(() => { refreshPromise = null; });
  return refreshPromise;
}

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config || {};
    const isAuthCall = (original.url || "").includes("/auth/login") || (original.url || "").includes("/auth/refresh");
    if (err.response?.status === 401 && !original._retry && !isAuthCall) {
      original._retry = true;
      const newToken = await tryRefresh();
      if (newToken) {
        original.headers = { ...(original.headers || {}), Authorization: `Bearer ${newToken}` };
        return api.request(original);
      }
      // Refresh failed → hard logout
      if (window.location.pathname !== "/login") {
        localStorage.removeItem("cpaas_token");
        localStorage.removeItem("cpaas_refresh_token");
        localStorage.removeItem("cpaas_user");
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export default api;
