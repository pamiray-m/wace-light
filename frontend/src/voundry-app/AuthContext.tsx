import React from "react";
import * as api from "./api";
import type { Principal, Role } from "./api";

interface AuthState {
  principal: Principal | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, role: Role, display_name: string, acceptedTerms: boolean) => Promise<void>;
  logout: () => void;
}

const Ctx = React.createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const v = React.useContext(Ctx);
  if (!v) throw new Error("useAuth must be used within AuthProvider");
  return v;
}

export function AuthProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const [principal, setPrincipal] = React.useState<Principal | null>(null);
  const [loading, setLoading] = React.useState<boolean>(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    (async () => {
      // OIDC SSO redirect lands with #sso_token=… — capture it, then clean the URL.
      try {
        const h = window.location.hash || "";
        const m = h.match(/[#&]sso_token=([^&]+)/);
        if (m) {
          api.setToken(decodeURIComponent(m[1]));
          const cleaned = h.replace(/[#&]sso_token=[^&]+/, "").replace(/^#$/, "");
          window.history.replaceState(null, "", window.location.pathname + window.location.search + cleaned);
        }
      } catch { /* ignore */ }
      if (!api.getToken()) { setLoading(false); return; }
      try { setPrincipal(await api.me()); }
      catch { api.logout(); }
      finally { setLoading(false); }
    })();
  }, []);

  const login = React.useCallback(async (email: string, password: string) => {
    setError(null);
    try { setPrincipal((await api.login(email, password)).principal); }
    catch (e) { setError(e instanceof Error ? e.message : "Login failed"); throw e; }
  }, []);

  const register = React.useCallback(async (email: string, password: string, role: Role, display_name: string, acceptedTerms: boolean) => {
    setError(null);
    try { setPrincipal((await api.register(email, password, role, display_name, acceptedTerms)).principal); }
    catch (e) { setError(e instanceof Error ? e.message : "Registration failed"); throw e; }
  }, []);

  const logout = React.useCallback(() => { api.logout(); setPrincipal(null); }, []);

  return <Ctx.Provider value={{ principal, loading, error, login, register, logout }}>{children}</Ctx.Provider>;
}
