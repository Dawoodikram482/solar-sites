// Login and registration share one form; `mode` switches between them.

import { useState, type FormEvent } from "react";
import * as api from "../api";
import { ApiError } from "../api";

interface Props {
  onLoggedIn: (email: string) => void; // tells App who is logged in
}

export default function AuthForm({ onLoggedIn }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault(); // stop the browser's own form submit (a page reload)
    setBusy(true);
    setError("");
    setFieldErrors({});
    try {
      const loggedIn = mode === "login" ? await api.login(email, password) : await api.register(email, password);
      onLoggedIn(loggedIn);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fieldErrors);
      } else {
        setError("Something went wrong.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <form className="card auth" onSubmit={handleSubmit}>
        <h1>Solar sites</h1>
        <h2>{mode === "login" ? "Log in" : "Create an account"}</h2>

        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          {fieldErrors.email && <span className="field-error">{fieldErrors.email}</span>}
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={mode === "register" ? 8 : undefined}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
          {mode === "register" && <span className="hint">At least 8 characters.</span>}
          {fieldErrors.password && <span className="field-error">{fieldErrors.password}</span>}
        </label>

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={busy}>
          {mode === "login" ? "Log in" : "Create account"}
        </button>
        <button
          type="button"
          className="link"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError("");
            setFieldErrors({});
          }}
        >
          {mode === "login" ? "No account yet? Create one" : "Already have an account? Log in"}
        </button>
      </form>
    </div>
  );
}
