// Details of one site: its data, the solar production, and the battery comparison.

import { useEffect, useState, type FormEvent } from "react";
import * as api from "../api";
import { ApiError } from "../api";
import type { BatteryResult, Production, Site } from "../types";

interface Props {
  site: Site;
  onEdit: () => void;
  onDelete: () => void;
  onSessionExpired: () => void;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Format a number Dutch-style for display, e.g. 4.512,3 -> "4.512".
const kwh = (value: number) => `${Math.round(value).toLocaleString("nl-NL")} kWh`;

export default function SiteDetail({ site, onEdit, onDelete, onSessionExpired }: Props) {
  const [production, setProduction] = useState<Production | null>(null);
  const [productionError, setProductionError] = useState("");

  // Battery form (as text, like in SiteForm) and its result.
  const [capacity, setCapacity] = useState("10");
  const [annualUse, setAnnualUse] = useState("3000");
  const [battery, setBattery] = useState<BatteryResult | null>(null);
  const [batteryErrors, setBatteryErrors] = useState<Record<string, string>>({});
  const [batteryError, setBatteryError] = useState("");
  const [batteryBusy, setBatteryBusy] = useState(false);

  // Fetch production whenever the site's values change (e.g. after an edit).
  useEffect(() => {
    // If the user switches site before PVGIS answers, ignore the old answer,
    // so it can never be shown under the wrong site.
    let ignore = false;
    setProduction(null);
    setProductionError("");
    api
      .getProduction(site.id)
      .then((result) => !ignore && setProduction(result))
      .catch((err) => {
        if (ignore) return;
        if (err instanceof ApiError && err.status === 401) onSessionExpired();
        else setProductionError(err instanceof Error ? err.message : "Could not load production.");
      });
    return () => {
      ignore = true; // React runs this "cleanup" before the next run / on unmount
    };
  }, [site.id, site.latitude, site.longitude, site.peakKwp]);

  async function handleBattery(event: FormEvent) {
    event.preventDefault();
    setBatteryBusy(true);
    setBatteryError("");
    setBatteryErrors({});
    try {
      setBattery(await api.getBattery(site.id, Number(capacity), Number(annualUse)));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return onSessionExpired();
      if (err instanceof ApiError) {
        setBatteryError(err.message);
        setBatteryErrors(err.fieldErrors);
      }
    } finally {
      setBatteryBusy(false);
    }
  }

  // Tallest month = 100 % bar width; the others relative to it.
  const maxMonth = production ? Math.max(...production.monthlyKwh.map((m) => m.kwh), 1) : 1;

  return (
    <div className="stack">
      <div className="card">
        <div className="row">
          <h2>{site.clientName}</h2>
          <div className="row">
            <button className="secondary" onClick={onEdit}>Edit</button>
            <button className="danger" onClick={onDelete}>Delete</button>
          </div>
        </div>
        <p>{site.address}</p>
        <p className="muted">
          {site.latitude}, {site.longitude} · {site.peakKwp} kWp
          {site.roofAreaM2 != null && ` · ${site.roofAreaM2} m² roof`}
        </p>
      </div>

      <div className="card">
        <h3>Estimated solar production</h3>
        {productionError && <p className="error">{productionError}</p>}
        {!production && !productionError && <p className="muted">Asking PVGIS…</p>}
        {production && (
          <>
            <p className="big">{kwh(production.yearlyKwh)} per year</p>
            <ul className="bars">
              {production.monthlyKwh.map((m) => (
                <li key={m.month}>
                  <span>{MONTHS[m.month - 1]}</span>
                  <span className="bar" style={{ width: `${(m.kwh / maxMonth) * 100}%` }} />
                  <span className="muted">{kwh(m.kwh)}</span>
                </li>
              ))}
            </ul>
            <p className="hint">PVGIS long-term average, optimal panel angle, 14 % system losses.</p>
          </>
        )}
      </div>

      <div className="card">
        <h3>Home battery</h3>
        <form className="two-col" onSubmit={handleBattery}>
          <label>
            Battery capacity (kWh)
            <input type="number" step="any" value={capacity} onChange={(e) => setCapacity(e.target.value)} />
            {batteryErrors.capacityKwh && <span className="field-error">{batteryErrors.capacityKwh}</span>}
          </label>
          <label>
            Household use per year (kWh)
            <input type="number" step="any" value={annualUse} onChange={(e) => setAnnualUse(e.target.value)} />
            {batteryErrors.annualUseKwh && <span className="field-error">{batteryErrors.annualUseKwh}</span>}
          </label>
          <button type="submit" disabled={batteryBusy}>{batteryBusy ? "Calculating…" : "Calculate"}</button>
        </form>
        {batteryError && <p className="error">{batteryError}</p>}

        {battery && (
          <>
            <p className="big">
              The battery adds {kwh(battery.batteryAddsKwh)} of own solar use per year
            </p>
            <table>
              <thead>
                <tr><th></th><th>Without battery</th><th>With {battery.capacityKwh} kWh battery</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td>Solar used at home</td>
                  <td>{kwh(battery.withoutBattery.selfUsedKwh)}</td>
                  <td>{kwh(battery.withBattery.selfUsedKwh)}</td>
                </tr>
                <tr>
                  <td>Share of solar used at home</td>
                  <td>{battery.withoutBattery.selfConsumptionPercent}%</td>
                  <td>{battery.withBattery.selfConsumptionPercent}%</td>
                </tr>
                <tr>
                  <td>Share of household use covered by solar</td>
                  <td>{battery.withoutBattery.selfSufficiencyPercent}%</td>
                  <td>{battery.withBattery.selfSufficiencyPercent}%</td>
                </tr>
                <tr>
                  <td>Sent to the grid</td>
                  <td>{kwh(battery.withoutBattery.gridExportKwh)}</td>
                  <td>{kwh(battery.withBattery.gridExportKwh)}</td>
                </tr>
                <tr>
                  <td>Bought from the grid</td>
                  <td>{kwh(battery.withoutBattery.gridImportKwh)}</td>
                  <td>{kwh(battery.withBattery.gridImportKwh)}</td>
                </tr>
              </tbody>
            </table>
            <p className="hint">
              Hour-by-hour simulation of {battery.year}: {kwh(battery.productionKwh)} solar,{" "}
              {kwh(battery.consumptionKwh)} household use (typical Dutch daily and seasonal pattern),
              90 % battery efficiency.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
