// The main screen: the list of sites on the left, and on the right either a
// form (new / edit) or the details of the selected site.

import { useEffect, useState } from "react";
import * as api from "../api";
import { ApiError } from "../api";
import type { Site, SiteInput } from "../types";
import SiteDetail from "./SiteDetail";
import SiteForm from "./SiteForm";

interface Props {
  onSessionExpired: () => void;
}

export default function SitesPage({ onSessionExpired }: Props) {
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // What the right-hand side shows: nothing, a "new site" form, or an edit form.
  const [editing, setEditing] = useState<"new" | Site | null>(null);
  const [error, setError] = useState("");

  // Shared error handling: 401 means the session is gone -> back to login.
  function handleError(err: unknown) {
    if (err instanceof ApiError && err.status === 401) onSessionExpired();
    else setError(err instanceof Error ? err.message : "Something went wrong.");
  }

  // Load the advisor's sites once, when this screen appears.
  useEffect(() => {
    api.listSites().then(setSites).catch(handleError);
  }, []);

  // Called by SiteForm. Throws on failure so the form can show field errors.
  async function handleSave(input: SiteInput) {
    if (editing === "new") {
      const created = await api.createSite(input);
      setSites([...sites, created]);
      setSelectedId(created.id);
    } else if (editing) {
      const updated = await api.updateSite(editing.id, input);
      // Replace the old version of this site in the list.
      setSites(sites.map((s) => (s.id === updated.id ? updated : s)));
    }
    setEditing(null);
  }

  async function handleDelete(site: Site) {
    if (!confirm(`Delete the site of ${site.clientName}?`)) return;
    try {
      await api.deleteSite(site.id);
      setSites(sites.filter((s) => s.id !== site.id));
      setSelectedId(null);
    } catch (err) {
      handleError(err);
    }
  }

  const selected = sites.find((s) => s.id === selectedId) ?? null;

  return (
    <main className="layout">
      <aside className="card">
        <div className="row">
          <h2>Client sites</h2>
          <button onClick={() => setEditing("new")}>+ New site</button>
        </div>
        {sites.length === 0 && <p className="muted">No sites yet. Add your first one.</p>}
        <ul className="site-list">
          {sites.map((site) => (
            <li key={site.id}>
              <button
                className={site.id === selectedId ? "site selected" : "site"}
                onClick={() => {
                  setSelectedId(site.id);
                  setEditing(null);
                }}
              >
                <strong>{site.clientName}</strong>
                <span className="muted">{site.address}</span>
              </button>
            </li>
          ))}
        </ul>
        {error && <p className="error">{error}</p>}
      </aside>

      <section>
        {editing ? (
          <SiteForm
            // key: a fresh form (fresh state) for each site being edited
            key={editing === "new" ? "new" : editing.id}
            initial={editing === "new" ? null : editing}
            onSave={handleSave}
            onCancel={() => setEditing(null)}
            onSessionExpired={onSessionExpired}
          />
        ) : selected ? (
          <SiteDetail
            key={selected.id}
            site={selected}
            onEdit={() => setEditing(selected)}
            onDelete={() => handleDelete(selected)}
            onSessionExpired={onSessionExpired}
          />
        ) : (
          <div className="card muted">Select a site, or add a new one.</div>
        )}
      </section>
    </main>
  );
}
