// Top-level component: decides between "log in" and "the app".
// There is no router library: the app has two screens, and a piece of state
// (`email`) is enough to pick between them.

import { useEffect, useState } from "react";
import * as api from "./api";
import AuthForm from "./components/AuthForm";
import SitesPage from "./components/SitesPage";

export default function App() {
  // null = not logged in. undefined = still checking with the server.
  const [email, setEmail] = useState<string | null | undefined>(undefined);

  // On first load, ask the server whether the browser already has a session
  // (the cookie survives a page reload; React state does not).
  useEffect(() => {
    api.me().then(setEmail).catch(() => setEmail(null));
  }, []); // [] = run once, after the first render

  async function handleLogout() {
    try {
      await api.logout();
    } finally {
      setEmail(null); // even if the call failed, show the login screen
    }
  }

  if (email === undefined) return <p className="center">Loading…</p>;

  if (email === null) return <AuthForm onLoggedIn={setEmail} />;

  return (
    <div className="app">
      <header className="topbar">
        <h1>Solar sites</h1>
        <span className="muted">{email}</span>
        <button className="secondary" onClick={handleLogout}>Log out</button>
      </header>
      {/* If a request says 401 (session expired), go back to the login screen. */}
      <SitesPage onSessionExpired={() => setEmail(null)} />
    </div>
  );
}
