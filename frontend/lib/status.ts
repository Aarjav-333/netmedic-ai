/** Status palette + labels. Colours are reserved for state and always paired with a label/icon. */

import type { HealthStatus, NodeType } from "@/lib/types";

export const STATUS_COLOR: Record<HealthStatus, string> = {
  healthy: "var(--status-good)",
  warning: "var(--status-warning)",
  critical: "var(--status-critical)",
  offline: "var(--status-offline)",
};

export const STATUS_LABEL: Record<HealthStatus, string> = {
  healthy: "Healthy",
  warning: "Warning",
  critical: "Critical",
  offline: "Offline",
};

export const NODE_TYPE_LABEL: Record<NodeType, string> = {
  gateway: "Gateway",
  router: "Router",
  switch: "Switch",
  server: "Server",
};

export function healthFromScore(score: number): HealthStatus {
  if (score < 50) return "critical";
  if (score < 85) return "warning";
  return "healthy";
}

export function formatNumber(value: number, digits = 0): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function formatMbps(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(2)} Gbps`;
  return `${formatNumber(value)} Mbps`;
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", { hour12: false });
}
