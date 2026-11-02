// Form to create or edit a site.
// The backend is the real validator: whatever it rejects comes back as one
// message per field, and we show each message under its input.

import { useState, type FormEvent } from "react";
import { ApiError } from "../api";
import type { Site, SiteInput } from "../types";

interface Props {
  initial: Site | null; // null = new site
  onSave: (input: SiteInput) => Promise<void>;
  onCancel: () => void;
  onSessionExpired: () => void;
}

// Inputs always hold text, so the form keeps every value as a string and
// converts to numbers only when submitting.
type FormValues = Record<keyof SiteInput, string>;

function toFormValues(site: Site | null): FormValues {
  return {
    clientName: site?.clientName ?? "",
    address: site?.address ?? "",
    latitude: site ? String(site.latitude) : "",
    longitude: site ? String(site.longitude) : "",
    roofAreaM2: site?.roofAreaM2 != null ? String(site.roofAreaM2) : "",
    peakKwp: site ? String(site.peakKwp) : "",
  };
}

// "" -> null, so the backend reports "required / must be a number"
// instead of us silently sending 0.
function toNumber(text: string): number | null {
  return text.trim() === "" ? null : Number(text);
}

export default function SiteForm({ initial, onSave, onCancel, onSessionExpired }: Props) {
  const [values, setValues] = useState<FormValues>(toFormValues(initial));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // One change handler for all inputs: the input's `name` says which field.
  function update(field: keyof SiteInput, value: string) {
    setValues({ ...values, [field]: value });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setFieldErrors({});
    try {
      await onSave({
        clientName: values.clientName,
        address: values.address,
        latitude: toNumber(values.latitude) as number,
        longitude: toNumber(values.longitude) as number,
        roofAreaM2: toNumber(values.roofAreaM2),
        peakKwp: toNumber(values.peakKwp) as number,
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return onSessionExpired();
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

  // A small helper so each field is one line below, not twelve.
  function field(name: keyof SiteInput, label: string, type = "text", extra: Record<string, string> = {}) {
    return (
      <label>
        {label}
        <input type={type} value={values[name]} onChange={(e) => update(name, e.target.value)} {...extra} />
        {fieldErrors[name] && <span className="field-error">{fieldErrors[name]}</span>}
      </label>
    );
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2>{initial ? `Edit ${initial.clientName}` : "New site"}</h2>
      {field("clientName", "Client name")}
      {field("address", "Address")}
      <div className="two-col">
        {field("latitude", "Latitude", "number", { step: "any", placeholder: "52.08" })}
        {field("longitude", "Longitude", "number", { step: "any", placeholder: "4.31" })}
      </div>
      <div className="two-col">
        {field("roofAreaM2", "Roof area in m² (optional)", "number", { step: "any" })}
        {field("peakKwp", "Panel capacity in kWp", "number", { step: "any" })}
      </div>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button type="submit" disabled={busy}>Save</button>
        <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
