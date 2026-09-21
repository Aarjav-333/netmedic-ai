/** Thin typed fetch helpers for the NetMedic REST API. */

import { getBackendConfig } from "@/lib/config";
import type { ActiveFault, DemoState, FaultDefinition, Incident, InjectFaultRequest } from "@/lib/types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { apiBaseUrl } = await getBackendConfig();
  const res = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  time: string;
}

export const getHealth = () => api.get<HealthResponse>("/api/health");

// ---- Faults ----
export interface FaultListResponse {
  active: ActiveFault[];
  catalog: FaultDefinition[];
}

export const getFaults = () => api.get<FaultListResponse>("/api/faults");
export const injectFault = (body: InjectFaultRequest) => api.post<ActiveFault>("/api/faults/inject", body);
export const clearFault = (id: string) => api.delete<ActiveFault>(`/api/faults/${id}`);
export const resetSimulation = () =>
  api.post<{ cleared_faults: number; message: string }>("/api/faults/reset");

// ---- Incidents / healing ----
export const getIncident = (id: string) => api.get<Incident>(`/api/incidents/${id}`);
export const executeHealing = (id: string) => api.post<Incident>(`/api/healing/${id}/execute`);
export const setAutoHeal = (auto_heal: boolean) =>
  api.post<{ auto_heal: boolean }>("/api/healing/mode", { auto_heal });

// ---- Demo ----
export interface DemoScenario {
  key: string;
  title: string;
  description: string;
  target_id: string;
}

export const getDemoScenarios = () => api.get<DemoScenario[]>("/api/demo/scenarios");
export const runDemo = (scenario: string) => api.post<DemoState>("/api/demo/run", { scenario });
export const stopDemo = () => api.post<DemoState>("/api/demo/stop");
