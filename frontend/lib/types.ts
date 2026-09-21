/** TypeScript mirrors of the backend Pydantic schemas. Keep in sync with backend/app/models. */

export type NodeType = "gateway" | "router" | "switch" | "server";
export type HealthStatus = "healthy" | "warning" | "critical" | "offline";
export type AdminStatus = "up" | "down";
export type FlowStatus = "ok" | "degraded" | "down";

export interface Position {
  x: number;
  y: number;
}

export interface NetworkNode {
  id: string;
  name: string;
  type: NodeType;
  capacity_mbps: number;
  status: AdminStatus;
  health: HealthStatus;
  position: Position;
  penalty: number;
  isolated: boolean;
}

export interface NetworkLink {
  id: string;
  source: string;
  target: string;
  base_latency_ms: number;
  capacity_mbps: number;
  status: AdminStatus;
  health: HealthStatus;
  penalty: number;
  isolated: boolean;
}

export interface Flow {
  id: string;
  name: string;
  source: string;
  destination: string;
  demand_mbps: number;
  rate_limit_mbps: number | null;
}

export interface Route {
  flow_id: string;
  path: string[];
  links: string[];
  cost: number;
  is_primary: boolean;
  reason: string;
}

export interface Topology {
  nodes: NetworkNode[];
  links: NetworkLink[];
  flows: Flow[];
  routes: Route[];
}

export interface NodeTelemetry {
  node_id: string;
  timestamp: string;
  status: AdminStatus;
  health: HealthStatus;
  latency_ms: number;
  packet_loss_percent: number;
  throughput_mbps: number;
  bandwidth_utilization_percent: number;
  cpu_percent: number;
  memory_percent: number;
  active_connections: number;
  health_score: number;
}

export interface LinkTelemetry {
  link_id: string;
  source: string;
  target: string;
  timestamp: string;
  status: AdminStatus;
  health: HealthStatus;
  latency_ms: number;
  packet_loss_percent: number;
  throughput_mbps: number;
  utilization_percent: number;
  capacity_mbps: number;
  health_score: number;
}

export interface FlowTelemetry {
  flow_id: string;
  name: string;
  source: string;
  destination: string;
  path: string[];
  links: string[];
  status: FlowStatus;
  health: HealthStatus;
  latency_ms: number;
  packet_loss_percent: number;
  throughput_mbps: number;
  demand_mbps: number;
  is_primary_route: boolean;
  health_score: number;
}

export interface NetworkSummary {
  health_score: number;
  flow_health: number;
  node_health: number;
  link_health: number;
  active_nodes: number;
  total_nodes: number;
  active_links: number;
  total_links: number;
  avg_latency_ms: number;
  avg_node_latency_ms: number;
  avg_packet_loss_percent: number;
  total_throughput_mbps: number;
  total_demand_mbps: number;
  rerouted_flows: number;
  broken_flows: number;
}

export interface TelemetrySnapshot {
  tick: number;
  timestamp: string;
  nodes: NodeTelemetry[];
  links: LinkTelemetry[];
  flows: FlowTelemetry[];
  summary: NetworkSummary;
}

export interface MetricPoint {
  tick: number;
  timestamp: string;
  health_score: number;
  avg_latency_ms: number;
  avg_packet_loss_percent: number;
  total_throughput_mbps: number;
  node_latency_ms: Record<string, number>;
  node_cpu_percent: Record<string, number>;
  node_utilization_percent: Record<string, number>;
  node_packet_loss_percent: Record<string, number>;
}

/** Message pushed over /ws/network every tick. */
export interface StateMessage {
  type: "state";
  tick: number;
  topology: Topology;
  telemetry: TelemetrySnapshot | null;
}
