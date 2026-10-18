/**
 * Where the browser reaches the NetMedic backend.
 *
 * Three tiers, most specific first:
 *   1. build time  NEXT_PUBLIC_API_BASE_URL / NEXT_PUBLIC_WS_URL
 *   2. runtime     /api/config → NETMEDIC_API_BASE_URL / NETMEDIC_WS_URL / NETMEDIC_BACKEND_PORT
 *   3. derived     window.location + the backend port
 *
 * `apiBaseUrl` comes from the first tier that sets it. `wsUrl` is taken from an explicit
 * value only when that value sits in the *same or a more specific* tier than the chosen
 * API base; otherwise it is derived from the API base. That pairing rule is what stops a
 * build-time API override and a runtime-only WS override from pointing at different hosts.
 *
 * Malformed values (wrong scheme, unparseable URL, out-of-range port) are rejected with a
 * console warning and fall back to the next tier, so a typo degrades to the derived default
 * instead of throwing inside `new WebSocket()`.
 *
 * Nothing host-specific is baked into the bundle: one image serves localhost, 127.0.0.1,
 * a LAN address or a port-forward without rebuilding.
 */

export const DEFAULT_BACKEND_PORT = 8000;

/** How long a failed /api/config lookup is remembered before trying again. */
const FAILURE_TTL_MS = 2000;
const CONFIG_TIMEOUT_MS = 3000;

export interface BackendConfig {
  apiBaseUrl: string;
  wsUrl: string;
}

interface RuntimeConfig {
  apiBaseUrl: string | null;
  wsUrl: string | null;
  backendPort: string | null;
}

function warn(message: string): void {
  if (typeof console !== "undefined") console.warn(`[netmedic] ${message}`);
}

/** Validate an http(s) base URL and strip trailing slashes so `${base}${path}` never doubles up. */
function normalizeApiBase(raw: string | null | undefined, source: string): string | null {
  if (!raw?.trim()) return null;
  try {
    const url = new URL(raw.trim());
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      warn(`Ignoring ${source}: expected an http(s) URL, got ${JSON.stringify(raw)}.`);
      return null;
    }
    return `${url.origin}${url.pathname.replace(/\/+$/, "")}`;
  } catch {
    warn(`Ignoring ${source}: ${JSON.stringify(raw)} is not a valid URL.`);
    return null;
  }
}

/** Validate a WebSocket URL, coercing http(s) → ws(s) since the variable name invites it. */
function normalizeWsUrl(raw: string | null | undefined, source: string): string | null {
  if (!raw?.trim()) return null;
  try {
    const url = new URL(raw.trim());
    if (url.protocol === "http:" || url.protocol === "https:") {
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    }
    if (url.protocol !== "ws:" && url.protocol !== "wss:") {
      warn(`Ignoring ${source}: expected a ws(s) URL, got ${JSON.stringify(raw)}.`);
      return null;
    }
    return url.toString();
  } catch {
    warn(`Ignoring ${source}: ${JSON.stringify(raw)} is not a valid URL.`);
    return null;
  }
}

/** http(s)://host[:port][/prefix] → ws(s)://host[:port][/prefix]/ws/network */
function wsUrlFor(apiBaseUrl: string): string {
  const url = new URL(apiBaseUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `${url.pathname.replace(/\/+$/, "")}/ws/network`;
  return url.toString();
}

function parsePort(raw: string | null | undefined): number {
  if (!raw?.trim()) return DEFAULT_BACKEND_PORT;
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    warn(`Ignoring backend port ${JSON.stringify(raw)}: not a port number. Using ${DEFAULT_BACKEND_PORT}.`);
    return DEFAULT_BACKEND_PORT;
  }
  return port;
}

function apiBaseFromLocation(port: number): string {
  if (typeof window === "undefined") return `http://localhost:${port}`;
  const { protocol, hostname } = window.location;
  return `${protocol === "https:" ? "https" : "http"}://${hostname}:${port}`;
}

const BUILD_API = normalizeApiBase(process.env.NEXT_PUBLIC_API_BASE_URL, "NEXT_PUBLIC_API_BASE_URL");
const BUILD_WS = normalizeWsUrl(process.env.NEXT_PUBLIC_WS_URL, "NEXT_PUBLIC_WS_URL");

function build(runtime: RuntimeConfig | null): BackendConfig {
  const port = parsePort(runtime?.backendPort);
  const tiers: { api: string | null; ws: string | null }[] = [
    { api: BUILD_API, ws: BUILD_WS },
    {
      api: normalizeApiBase(runtime?.apiBaseUrl, "NETMEDIC_API_BASE_URL"),
      ws: normalizeWsUrl(runtime?.wsUrl, "NETMEDIC_WS_URL"),
    },
    { api: apiBaseFromLocation(port), ws: null },
  ];
  const apiTier = tiers.findIndex((t) => t.api !== null);
  const wsTier = tiers.findIndex((t) => t.ws !== null);
  const apiBaseUrl = tiers[apiTier].api as string;
  const explicitWs = wsTier !== -1 && wsTier <= apiTier ? tiers[wsTier].ws : null;
  return { apiBaseUrl, wsUrl: explicitWs ?? wsUrlFor(apiBaseUrl) };
}

async function fetchRuntimeConfig(): Promise<RuntimeConfig | null> {
  if (typeof window === "undefined") return null;
  try {
    // Without a timeout a stalled Next server (mid-HMR, overloaded, proxied) would hang
    // every caller forever - and the socket's only retry path is `onclose`.
    const res = await fetch("/api/config", { cache: "no-store", signal: AbortSignal.timeout(CONFIG_TIMEOUT_MS) });
    if (!res.ok) return null;
    return (await res.json()) as RuntimeConfig;
  } catch {
    return null;
  }
}

let resolved: BackendConfig | null = null;
let inFlight: Promise<BackendConfig> | null = null;
let failedAt = 0;

/**
 * Resolved once per page load. A successful lookup is cached for the lifetime of the page;
 * a failed one is retried after FAILURE_TTL_MS (so a dev-server restart heals itself without
 * turning every REST call into two round trips). Concurrent callers share one request.
 */
export function getBackendConfig(): Promise<BackendConfig> {
  if (resolved) return Promise.resolve(resolved);
  if (inFlight) return inFlight;
  if (failedAt && Date.now() - failedAt < FAILURE_TTL_MS) return Promise.resolve(build(null));

  inFlight = fetchRuntimeConfig()
    .then((runtime) => {
      const config = build(runtime);
      if (runtime === null) {
        failedAt = Date.now();
      } else {
        resolved = config;
        failedAt = 0;
      }
      return config;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

/** True once /api/config has answered; panels use it to retry one-shot loads. */
export function isBackendConfigResolved(): boolean {
  return resolved !== null;
}
