import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/components/auth";
import { Button, inputClass } from "@/components/ui";
import { usingMockData } from "@/lib/api";

export function LoginPage() {
  const { status, login, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === "signedIn") return <Navigate to={from} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      const message = (err as Error).message;
      setError(message === "Failed to fetch" ? "The KnowledgePulse API is not reachable. Is the backend running?" : message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-paper-sunk px-5 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="flex items-baseline justify-center gap-0.5">
            <span className="font-display text-h2 font-semibold tracking-tight">Knowledge</span>
            <span className="font-display text-h2 text-oxblood">Pulse</span>
          </p>
          <p className="mt-2 text-small text-ink-soft">Sign in to your organisation</p>
        </div>

        <form onSubmit={submit} noValidate className="space-y-4 rounded-md border border-rule bg-paper-raised p-6">
          {notice && !error && (
            <p role="status" className="rounded border-l-2 border-ochre bg-ochre-wash/60 px-3 py-2 text-small text-[#7A5A17]">
              {notice}
            </p>
          )}
          {error && (
            <p role="alert" className="rounded border-l-2 border-oxblood bg-oxblood-wash px-3 py-2 text-small text-oxblood-deep">
              {error}
            </p>
          )}

          <div>
            <label htmlFor="login-email" className="text-small text-ink-soft">
              Email
            </label>
            <input
              id="login-email"
              type="email"
              autoComplete="username"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={`${inputClass} mt-1`}
            />
          </div>
          <div>
            <label htmlFor="login-password" className="text-small text-ink-soft">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`${inputClass} mt-1`}
            />
          </div>

          <Button type="submit" busy={busy} className="w-full">
            Sign in
          </Button>
        </form>

        {(usingMockData || import.meta.env.DEV) && (
          <p className="mt-4 text-center text-micro text-ink-faint">
            {usingMockData
              ? "Placeholder mode: any email and password will do."
              : "Local development: use the demo account from backend/.env (DEMO_USER_EMAIL, DEMO_USER_PASSWORD)."}
          </p>
        )}
      </div>
    </main>
  );
}
