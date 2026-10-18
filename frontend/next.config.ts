import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output keeps the Docker image small (see frontend/Dockerfile).
  output: "standalone",
  // `next dev` only serves dev assets to the hostname it was started with (localhost), so
  // opening the dashboard at 127.0.0.1 or a LAN address would render but never hydrate.
  // Hostnames only - scheme and port are ignored. Production (`next start`) is unaffected.
  // Kept in step with the backend CORS regex (docker-compose.yml) so a host that passes
  // CORS cannot still be blocked here: 172.16-31 covers Docker bridges and VPN pools.
  allowedDevOrigins: [
    "127.0.0.1",
    "[::1]",
    "*.local",
    "10.*.*.*",
    "192.168.*.*",
    ...Array.from({ length: 16 }, (_, i) => `172.${16 + i}.*.*`),
  ],
};

export default nextConfig;
