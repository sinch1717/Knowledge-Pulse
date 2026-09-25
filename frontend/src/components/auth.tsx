import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { api, getSession, onSessionEnded } from "@/lib/api";
import type { AuthUser } from "@/lib/types";

type Status = "checking" | "signedIn" | "signedOut";

interface AuthState {
  status: Status;
  user: AuthUser | null;
  /** Why the last session ended, shown once on the sign-in page. */
  notice: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Holds the signed-in user. Wraps every route, including the sign-in page. */
export function AuthProvider() {
  const stored = getSession();
  const [user, setUser] = useState<AuthUser | null>(stored?.user ?? null);
  const [status, setStatus] = useState<Status>(stored ? "checking" : "signedOut");
  const [notice, setNotice] = useState<string | null>(null);

  // A stored session is confirmed with the server once per page load. If the
  // server is unreachable the session is kept, so the app can show its own
  // "backend unreachable" states instead of bouncing to sign-in.
  useEffect(() => {
    if (!stored) return;
    let alive = true;
    api
      .me()
      .then((u) => {
        if (!alive) return;
        setUser(u);
        setStatus("signedIn");
      })
      .catch(() => {
        if (alive) setStatus(getSession() ? "signedIn" : "signedOut");
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Any request that comes back 401 ends the session here too.
  useEffect(
    () =>
      onSessionEnded((reason) => {
        setUser(null);
        setStatus("signedOut");
        setNotice(reason);
      }),
    [],
  );

  const login = useCallback(async (email: string, password: string) => {
    const u = await api.login(email, password);
    setUser(u);
    setNotice(null);
    setStatus("signedIn");
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setUser(null);
    setNotice("You have signed out.");
    setStatus("signedOut");
  }, []);

  return (
    <AuthContext.Provider value={{ status, user, notice, login, logout }}>
      <Outlet />
    </AuthContext.Provider>
  );
}

/** Gate for every page except sign-in. */
export function RequireAuth({ children }: { children?: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "checking") {
    return (
      <div role="status" className="grid min-h-screen place-items-center text-small text-ink-faint">
        Checking your session
      </div>
    );
  }
  if (status === "signedOut") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return children ? <>{children}</> : <Outlet />;
}
