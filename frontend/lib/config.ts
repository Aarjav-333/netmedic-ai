/**
 * Where the browser reaches the NetMedic backend.
 *
 * Resolution order (first non-empty wins):
 *   1. NEXT_PUBLIC_API_BASE_URL / NEXT_PUBLIC_WS_URL  — build-time overrides (local dev convenience)
 *   2. /api/config                                     — runtime values from the frontend server's env
 *                                                        (NETMEDIC_API_BASE_URL, NETMEDIC_WS_URL, NETMEDIC_BACKEND_PORT)
 *   3. window.location                                 — same host as the dashboard, backend port (default 8000)
 *
 * The WebSocket URL, when not given explicitly, is always derived from the resolved API
 * base URL so that overriding only the API host never leaves the stream pointing elsewhere.
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

function apiBaseFromLocation(port: number): string {
  if (typeof window === "undefined") return `http://localhost:${port}`;
  const { protocol, hostname } = window.location;
  return `${protocol === "https:" ? "https" : "http"}://${hostname}:${port}`;
}

/** http(s)://host[:port][/prefix] → ws(s)://host[:port][/prefix]/ws/network */
function wsUrlFor(apiBaseUrl: string): string {
  return `${apiBaseUrl.replace(/^http/, "ws").replace(/\/+$/, "")}/ws/network`;
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

function build(runtime: RuntimeConfig | null): BackendConfig {
  const port = Number(runtime?.backendPort) || DEFAULT_BACKEND_PORT;
  const apiBaseUrl = BUILD_API ?? runtime?.apiBaseUrl ?? apiBaseFromLocation(port);
  return { apiBaseUrl, wsUrl: BUILD_WS ?? runtime?.wsUrl ?? wsUrlFor(apiBaseUrl) };
}

/**
 * Resolved once per page load and cached. A failed /api/config fetch (dev server
 * restarting, HMR reconnect) is *not* cached: the caller gets location-derived
 * defaults for now and the next call — typically the socket retry — resolves again.
 */
export function getBackendConfig(): Promise<BackendConfig> {
  if (cached) return cached;
  const pending: Promise<BackendConfig> = fetchRuntimeConfig().then((runtime) => {
    if (runtime === null && cached === pending) cached = null;
    return build(runtime);
  });
  cached = pending;
  return pending;
}
