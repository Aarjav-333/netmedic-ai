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
  faults: ActiveFault[];
  detection: DetectionResult | null;
  diagnosis: Diagnosis | null;
  incident: Incident | null;
  incidents: IncidentSummary[];
  quarantined: string[];
  auto_heal: boolean;
}

// ---- Faults ----
export type FaultType =
  | "router_congestion"
  | "link_failure"
  | "packet_loss_spike"
  | "bandwidth_degradation"
  | "node_overload"
  | "traffic_spike"
  | "router_failure";
export type Severity = "low" | "medium" | "high";
export type TargetKind = "node" | "link";

export interface FaultDefinition {
  type: FaultType;
  label: string;
  description: string;
  target_kind: TargetKind;
  node_types: NodeType[];
}

export interface ActiveFault {
  id: string;
  type: FaultType;
  label: string;
  target_id: string;
  target_kind: TargetKind;
  severity: Severity;
  injected_at: string;
  expires_at: string | null;
  cleared_at: string | null;
  cleared_by: string | null;
}

export interface InjectFaultRequest {
  fault_type: FaultType;
  target_id: string;
  severity?: Severity;
  duration_seconds?: number;
}

// ---- Detection ----
export type ComponentKind = "node" | "link" | "flow";

export interface MetricDeviation {
  metric: string;
  unit: string;
  baseline: number;
  current: number;
  ratio: number;
  direction: "up" | "down";
}

export interface ComponentAnomaly {
  component_id: string;
  component_kind: ComponentKind;
  method: string;
  decision_score: number | null;
  severity: number;
  is_anomaly: boolean;
  confirmed: boolean;
  consecutive_ticks: number;
  deviations: MetricDeviation[];
  reasons: string[];
}

export interface DetectionResult {
  tick: number;
  timestamp: string;
  anomalies: ComponentAnomaly[];
  node_scores: Record<string, number>;
  confirmed_ids: string[];
}

// ---- Diagnosis ----
export type RootCause =
  | "router_congestion"
  | "node_overload"
  | "traffic_spike"
  | "node_failure"
  | "link_failure"
  | "packet_loss_spike"
  | "bandwidth_saturation"
  | "unknown";

export type ActionType =
  | "reroute_around_node"
  | "reroute_around_link"
  | "isolate_link"
  | "restart_node"
  | "rate_limit_source"
  | "redistribute_load"
  | "escalate"
  | "monitor";

export type RiskLevel = "low" | "medium" | "high";

export interface RuleCheck {
  condition: string;
  weight: number;
  strength: number;
  observation: string;
}

export interface Hypothesis {
  root_cause: RootCause;
  target_id: string;
  target_kind: ComponentKind;
  score: number;
  checks: RuleCheck[];
}

export interface RemediationPlan {
  action: ActionType;
  target_id: string;
  target_kind: ComponentKind;
  summary: string;
  rationale: string;
  risk: RiskLevel;
  expected_outcome: string;
  parameters: Record<string, number | string>;
}

export interface Diagnosis {
  tick: number;
  timestamp: string;
  root_cause: RootCause;
  root_cause_label: string;
  target_id: string;
  target_kind: ComponentKind;
  confidence: number;
  confidence_explanation: string;
  evidence: string[];
  affected_flows: string[];
  affected_components: string[];
  hypotheses: Hypothesis[];
  anomaly_severity: number;
  plan: RemediationPlan;
}

// ---- AI ----
export interface AIExplanation {
  provider: string;
  model: string | null;
  diagnosis: string;
  explanation: string;
  evidence_summary: string[];
  remediation_justification: string;
  operational_risk: string;
  recovery_expectation: string;
  generated_at: string;
  latency_ms: number;
  fallback: boolean;
  error: string | null;
}

// ---- Incidents ----
export type IncidentStatus =
  | "detected"
  | "analyzing"
  | "diagnosed"
  | "remediating"
  | "verifying"
  | "resolved"
  | "partially_resolved"
  | "failed"
  | "cancelled";

export interface IncidentEvent {
  timestamp: string;
  tick: number;
  stage: IncidentStatus;
  message: string;
}

export interface RouteChange {
  flow_id: string;
  before: string[];
  after: string[];
}

export interface HealingActionRecord {
  id: string;
  incident_id: string;
  action: ActionType;
  target_id: string;
  target_kind: ComponentKind;
  parameters: Record<string, number | string>;
  started_at: string;
  completed_at: string | null;
  result: "applied" | "skipped" | "failed" | "restored";
  details: string;
  route_changes: RouteChange[];
}

export interface MetricWindow {
  samples: number;
  health_score: number;
  avg_latency_ms: number;
  avg_packet_loss_percent: number;
  affected_flows_healthy: number;
  affected_flows_total: number;
  target_latency_ms: number | null;
  target_packet_loss_percent: number | null;
  target_cpu_percent: number | null;
  target_utilization_percent: number | null;
}

export interface RecoveryCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface RecoveryReport {
  status: IncidentStatus;
  baseline: MetricWindow | null;
  before: MetricWindow;
  after: MetricWindow;
  checks: RecoveryCheck[];
  verified_at: string;
  summary: string;
}

export interface IncidentMetrics {
  time_to_detect_s: number | null;
  time_to_diagnose_s: number | null;
  time_to_remediate_s: number | null;
  recovery_time_s: number | null;
  total_duration_s: number | null;
}

export interface Incident {
  id: string;
  status: IncidentStatus;
  status_label: string;
  component_id: string;
  component_kind: ComponentKind;
  anomaly_severity: number;
  first_abnormal_at: string;
  detected_at: string;
  diagnosed_at: string | null;
  remediated_at: string | null;
  verified_at: string | null;
  resolved_at: string | null;
  root_cause: RootCause | null;
  root_cause_label: string | null;
  confidence: number | null;
  diagnosis: Diagnosis | null;
  plan: RemediationPlan | null;
  actions: HealingActionRecord[];
  recovery: RecoveryReport | null;
  timeline: IncidentEvent[];
  metrics: IncidentMetrics;
  ai_explanation: AIExplanation | null;
  auto_heal: boolean;
}

export interface IncidentSummary {
  id: string;
  status: IncidentStatus;
  status_label: string;
  component_id: string;
  root_cause_label: string | null;
  confidence: number | null;
  detected_at: string;
  resolved_at: string | null;
  action: ActionType | null;
  recovery_time_s: number | null;
  total_duration_s: number | null;
}
