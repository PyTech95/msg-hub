import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";

const AuthCtx = createContext(null);

// SECURITY: Access + refresh tokens live in httpOnly cookies (set by /auth/login,
// /auth/refresh). We never store them in localStorage. Only the user PROFILE is
// cached in localStorage to avoid a flash of unauthenticated state on reload.
export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const u = localStorage.getItem("cpaas_user");
    return u ? JSON.parse(u) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // On mount, hit /auth/me — the httpOnly cookie authenticates the request.
    // If the cookie is missing/expired, /auth/me returns 401 and api.js triggers
    // a refresh attempt; if that also fails, we clear the cached profile.
    api.get("/auth/me")
      .then((r) => { setUser(r.data); localStorage.setItem("cpaas_user", JSON.stringify(r.data)); })
      .catch(() => { localStorage.removeItem("cpaas_user"); setUser(null); })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email, password, otp) => {
    const { data } = await api.post("/auth/login", { email, password, otp });
    if (data.otp_required) return { otp_required: true };
    // NOTE: `data.token` + `data.refresh_token` are still returned in the response
    // body for backwards compatibility, but we ignore them here — httpOnly cookies
    // set on the same response are the authoritative credential store.
    localStorage.setItem("cpaas_user", JSON.stringify(data.user));
    setUser(data.user);
    return { user: data.user };
  }, []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch {}
    localStorage.removeItem("cpaas_user");
    setUser(null);
  }, []);

  return (
    <AuthCtx.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
