// Every call to the backend goes through this file.
// Components never call fetch() themselves, so cookies, the CSRF header and
// error handling are written once, here.

import type { BatteryResult, Production, Site, SiteInput } from "./types";

// The CSRF token lives only in memory (a variable), never in localStorage.
// After a page reload it is gone, and App gets it back from GET /api/me.
let csrfToken = "";

// An error from the API: HTTP status, a general message, and (for 422
// validation errors) one message per field, e.g. { latitude: "..." }.
export class ApiError extends Error {
  status: number;
  fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin", // send the session cookie
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection.");
  }

  if (response.status === 204) return undefined as T; // "No Content"

  // Read the JSON body (if any) for both success and error answers.
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = data?.detail ?? `Request failed (HTTP ${response.status})`;
    throw new ApiError(response.status, message, data?.errors ?? {});
  }
  return data as T;
}

type SessionAnswer = { email: string; csrfToken: string };

// --- Auth ---
// Each of these stores the CSRF token the server returns, then returns the email.

export async function register(email: string, password: string): Promise<string> {
  const answer = await request<SessionAnswer>("POST", "/api/register", { email, password });
  csrfToken = answer.csrfToken;
  return answer.email;
}

export async function login(email: string, password: string): Promise<string> {
  const answer = await request<SessionAnswer>("POST", "/api/login", { email, password });
  csrfToken = answer.csrfToken;
  return answer.email;
}

export async function me(): Promise<string> {
  const answer = await request<SessionAnswer>("GET", "/api/me");
  csrfToken = answer.csrfToken;
  return answer.email;
}

export async function logout(): Promise<void> {
  await request<void>("POST", "/api/logout");
  csrfToken = "";
}

// --- Sites ---

export const listSites = () => request<Site[]>("GET", "/api/sites");
export const createSite = (site: SiteInput) => request<Site>("POST", "/api/sites", site);
export const updateSite = (id: number, site: SiteInput) => request<Site>("PUT", `/api/sites/${id}`, site);
export const deleteSite = (id: number) => request<void>("DELETE", `/api/sites/${id}`);
export const getProduction = (id: number) => request<Production>("GET", `/api/sites/${id}/production`);

export function getBattery(id: number, capacityKwh: number, annualUseKwh: number) {
  // URLSearchParams encodes the values safely into the query string.
  const query = new URLSearchParams({
    capacityKwh: String(capacityKwh),
    annualUseKwh: String(annualUseKwh),
  });
  return request<BatteryResult>("GET", `/api/sites/${id}/battery?${query}`);
}
