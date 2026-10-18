import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output keeps the Docker image small (see frontend/Dockerfile).
  output: "standalone",
  // `next dev` only serves dev assets to the hostname it was started with (localhost), so
  // opening the dashboard at 127.0.0.1 or a LAN address would render but never hydrate.
  // Hostnames only - scheme and port are ignored. Production (`next start`) is unaffected.
  allowedDevOrigins: ["127.0.0.1", "[::1]", "*.local", "10.*.*.*", "192.168.*.*"],
};

export default nextConfig;
