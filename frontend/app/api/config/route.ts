/**
 * Runtime configuration for the browser.
 *
 * Read at request time from the *server* environment, so the same frontend
 * image works for any backend host/port without a rebuild. Empty values mean
 * "derive from window.location" on the client (see lib/config.ts).
 */

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json({
    apiBaseUrl: process.env.NETMEDIC_API_BASE_URL || null,
    wsUrl: process.env.NETMEDIC_WS_URL || null,
    backendPort: process.env.NETMEDIC_BACKEND_PORT || null,
  });
}
