import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const u = localStorage.getItem("cpaas_user");
    return u ? JSON.parse(u) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("cpaas_token");
    if (!token) { setLoading(false); return; }
    api.get("/auth/me")
      .then((r) => { setUser(r.data); localStorage.setItem("cpaas_user", JSON.stringify(r.data)); })
      .catch(() => { localStorage.removeItem("cpaas_token"); localStorage.removeItem("cpaas_refresh_token"); localStorage.removeItem("cpaas_user"); setUser(null); })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email, password, otp) => {
    const { data } = await api.post("/auth/login", { email, password, otp });
    if (data.otp_required) return { otp_required: true };
    localStorage.setItem("cpaas_token", data.token);
    if (data.refresh_token) localStorage.setItem("cpaas_refresh_token", data.refresh_token);
    localStorage.setItem("cpaas_user", JSON.stringify(data.user));
    setUser(data.user);
    return { user: data.user };
  }, []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch {}
    localStorage.removeItem("cpaas_token");
    localStorage.removeItem("cpaas_refresh_token");
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
