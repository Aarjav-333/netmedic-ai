/**
 * Where the browser reaches the NetMedic backend.
 *
 * Resolution order (first non-empty wins):
 *   1. NEXT_PUBLIC_API_BASE_URL / NEXT_PUBLIC_WS_URL  — build-time overrides (local dev convenience)
 *   2. /api/config                                     — runtime values from the frontend server's env
 *                                                        (NETMEDIC_API_BASE_URL, NETMEDIC_WS_URL, NETMEDIC_BACKEND_PORT)
 *   3. window.location                                 — same host as the dashboard, backend port (default 8000)
 *
 * Nothing host-specific is baked into the bundle, so one image serves localhost,
 * 127.0.0.1, a LAN address or a port-forward without rebuilding.
 */

export const DEFAULT_BACKEND_PORT = 8000;

export interface BackendConfig {
  apiBaseUrl: string;
  wsUrl: string;
}

interface RuntimeConfig {
  apiBaseUrl: string | null;
  wsUrl: string | null;
  backendPort: string | null;
}

const BUILD_API = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;
const BUILD_WS = process.env.NEXT_PUBLIC_WS_URL?.trim() || null;

let cached: Promise<BackendConfig> | null = null;

function deriveFromLocation(port: number): BackendConfig {
  if (typeof window === "undefined") {
    return { apiBaseUrl: `http://localhost:${port}`, wsUrl: `ws://localhost:${port}/ws/network` };
  }
  const { protocol, hostname } = window.location;
  const secure = protocol === "https:";
  return {
    apiBaseUrl: `${secure ? "https" : "http"}://${hostname}:${port}`,
    wsUrl: `${secure ? "wss" : "ws"}://${hostname}:${port}/ws/network`,
  };
}

async function fetchRuntimeConfig(): Promise<RuntimeConfig | null> {
  if (typeof window === "undefined") return null;
  try {
    const res = await fetch("/api/config", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as RuntimeConfig;
  } catch {
    return null;
  }
}

async function resolve(): Promise<BackendConfig> {
  const runtime = await fetchRuntimeConfig();
  const port = Number(runtime?.backendPort) || DEFAULT_BACKEND_PORT;
  const derived = deriveFromLocation(port);
  return {
    apiBaseUrl: BUILD_API ?? runtime?.apiBaseUrl ?? derived.apiBaseUrl,
    wsUrl: BUILD_WS ?? runtime?.wsUrl ?? derived.wsUrl,
  };
}

/** Resolved once per page load and cached. */
export function getBackendConfig(): Promise<BackendConfig> {
  if (!cached) cached = resolve();
  return cached;
}
