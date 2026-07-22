import axios from "axios";

// Empty/unset REACT_APP_BACKEND_URL → same-origin relative "/api" (production VPS)
const BASE = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
export const API = `${BASE}/api`;

// SECURITY: Access + refresh tokens live in httpOnly, SameSite=Lax cookies set by
// the backend on /auth/login and /auth/refresh. `withCredentials: true` sends
// them on every request. No token is ever exposed to JS/localStorage — this
// mitigates XSS-based token theft.
const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Auto-refresh on 401 — single-flight (all concurrent requests wait on the same refresh call)
let refreshPromise = null;
async function tryRefresh() {
  if (refreshPromise) return refreshPromise;
  // POST with an empty body — the refresh_token httpOnly cookie is sent by the browser.
  refreshPromise = axios
    .post(`${API}/auth/refresh`, {}, { withCredentials: true })
    .then((r) => r.data.token || true)
    .catch(() => null)
    .finally(() => { refreshPromise = null; });
  return refreshPromise;
}

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config || {};
    const url = original.url || "";
    const isAuthCall = url.includes("/auth/login") || url.includes("/auth/refresh");
    if (err.response?.status === 401 && !original._retry && !isAuthCall) {
      original._retry = true;
      const ok = await tryRefresh();
      if (ok) return api.request(original);
      // Refresh failed → hard logout
      if (window.location.pathname !== "/login") {
        localStorage.removeItem("cpaas_user");
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export default api;
