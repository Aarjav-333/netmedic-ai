# NetMedic AI — Project Context

> Persistent project memory. Read this first in every new AI session. Update after every major change.

## Project

- **Name:** NetMedic AI — Autonomous Network Detection, Diagnosis & Self-Healing Platform
- **Hackathon:** Infosys IGNITE ENGNEXT 2026 – Hack-AI-Thon
- **Problem statement:** NC-04 — Self-Healing Network Simulator
- **Objective:** Functional MVP that continuously monitors a simulated network, detects degradation, diagnoses the root cause from telemetry (never from injected fault labels), executes a real corrective action on the simulated graph (rerouting is the primary one), and verifies recovery. Lifecycle: MONITOR → DETECT → DIAGNOSE → DECIDE → HEAL → VERIFY.

## Current Architecture

- **Frontend:** Next.js 16.3 (App Router) + React 19 + TypeScript + Tailwind v4 + shadcn/ui v4 (radix base, `cn` from the `cn` package); `@xyflow/react` 12 for topology; `recharts` 3 for metrics. Consumes REST + WebSocket only — renders backend state, never simulates locally. Dark theme by default.
- **Backend:** Python 3.11, FastAPI, Pydantic v2, Uvicorn. A single `SimulationEngine` singleton (`backend/app/engine.py`) runs a background asyncio tick loop (1.5 s). Each `tick()` in order: fault expiry → `HealingEngine.tick` (restarts, auto-restore) → fault effects → telemetry → detection → RCA (excluding quarantined components) → `IncidentManager.process` → publish state to WebSocket subscribers.
- **Network simulator:** NetworkX-backed `NetworkSimulator` (10 nodes / 15 links / 6 flows). Routing table is *static* between recomputations; `recompute_routes()` runs Dijkstra with weight = base_latency + congestion_penalty(util) + loss_penalty + link.penalty + target_node.penalty. DOWN nodes/links are excluded.
- **Telemetry:** physics-based generator: node load = routed flows (from routing table) + background + fault effects; utilisation → queueing latency, saturation loss, CPU; flows measured end-to-end along their current route. AR(1) noise. Health score documented in `backend/app/telemetry/health.py` (0.45 flows + 0.35 nodes + 0.20 links; per-component score = 100 × (1 − worst metric excess)).
- **ML:** scikit-learn Isolation Forest on 7 baseline-normalised node features (`backend/app/detection/features.py`), trained on synthetic fault-free runs (6 seeds × 400 ticks, per-flow demand jitter + diurnal swing). Persisted to `backend/data/models/isolation_forest.joblib` (+ `.json` metadata), auto-trained on first boot (~17 s). Links/flows use rules. 2-tick confirmation. Severity 0–100 = linear from the decision threshold to the model's worst-case score (documented as *not* a probability).
- **RCA:** deterministic hypothesis scoring (`backend/app/diagnosis/rules.py`): weighted soft rules per (component, hypothesis); confidence = best_score × (0.6 + 0.4 × (1 − runner_up/best)); formula spelled out in each diagnosis. Planner simulates reroutes before recommending; escalates when no alternative path exists.
- **Healing:** `HealingEngine` mutates real simulator state (penalties + route recompute, link isolation, node restart, rate limits). Quarantine with hold-down (restore after 6 clean ticks & ≥10-tick hold; 60-tick hold if flapping).
- **Verification:** windows of averaged samples (baseline 5 pre-anomaly, before 3, after 3 following a 2-tick settle). Four explicit checks → RESOLVED / PARTIALLY_RESOLVED / FAILED.
- **Incidents:** `IncidentManager` state machine advances one stage per tick: DETECTED → ANALYZING → DIAGNOSED → REMEDIATING → VERIFYING → RESOLVED/PARTIALLY_RESOLVED/FAILED (+ CANCELLED on reset). One active incident at a time; closed incidents kept in memory (SQLite persistence pending — Phase 10).
- **AI provider:** not yet implemented (Phase 9). Hook points exist: `IncidentManager.on_diagnosed`, `Incident.ai_explanation`.
- **Database:** not yet wired (Phase 10). Hook: `IncidentManager.on_change`.
- **WebSocket:** `/ws/network` pushes the full state message every tick: `{type, tick, topology, telemetry, faults, detection, diagnosis, incident, incidents, quarantined, auto_heal}`.

## Current Repository

- **GitHub:** https://github.com/Aarjav-333/netmedic-ai (public)
- **Branch:** `main`
- **Backend modules:** `backend/app/{api,simulation,telemetry,detection,diagnosis,healing,incidents,ai,database,models}`; tests in `backend/tests`
- **Frontend:** `frontend/{app,components/dashboard,components/ui,hooks,lib}`
- **Scripts:** `scripts/train_detector.py`

## Current Project Status

Phases 0–8 complete on the backend (simulator, telemetry, fault injection, detection, RCA, healing, verification, incidents). Frontend has topology/metrics/fault injector; diagnosis, healing and incident panels pending. ~60% complete.

## Completed

- Phase 0: public repo, README, CONTEXT, .gitignore, .env.example, LICENSE, backend + frontend scaffolds
- Phase 1: topology, routing, `GET /api/network/{topology,status}`
- Phase 2: telemetry generator, health score, tick loop, `GET /api/telemetry/{current,history}`, `WS /ws/network`
- Phase 3: dashboard base — WebSocket hook, top bar, stat tiles, React Flow topology (animated routes, reroute highlight), Recharts small multiples with node filter
- Phase 4: fault injector (7 fault types, severity, expiry) + API + frontend panel
- Phase 5: Isolation Forest detection + training script + `GET /api/detection/{current,model}`
- Phase 6: RCA engine + planner + `GET /api/diagnosis/current`
- Phase 7: healing engine (reroute / isolate / restart / rate-limit) + quarantine/restore
- Phase 8: recovery verification + incident state machine + `GET /api/incidents*`, `POST /api/healing/{id}/execute`, `GET/POST /api/healing/mode`

## In Progress

- Phase 9: AI explanation provider abstraction (Mock + env-driven Qualcomm)

## Next Tasks

1. Phase 9 — `AIExplanationProvider` (`backend/app/ai/`): MockProvider default; QualcommProvider configured only via env; async call at DIAGNOSED; result stored in `Incident.ai_explanation`
2. Phase 10 — SQLite persistence (SQLAlchemy): incidents, healing actions, events, telemetry snapshots (summarised); load history on boot
3. Frontend — AI diagnosis panel, healing panel (state badges, route change, recovery report), incident timeline, incident history; highlight affected node in topology
4. Phase 11 — demo mode (`POST /api/demo/run`): reset → healthy pause → inject R4 congestion → real pipeline
5. Phase 12 — polish, Docker, README screenshots, CONTEXT final

## Important Technical Decisions

- **Single engine, single tick loop** so the UI always reflects consistent backend state.
- **Ground truth isolation.** `FaultInjector.effects()` exposes only physics (extra load, capacity multiplier, loss adds…). Detection/RCA/healing never import fault labels. Tests assert no fault vocabulary leaks into detection output.
- **Static routing table.** Routes only change when the healing engine recomputes them, which is what makes rerouting a genuine remediation. Link/node failure black-holes flows until healed.
- **One global Isolation Forest on normalised features** (latency/base RTT, loss, throughput/capacity, utilisation, CPU, memory, connections/expected) instead of per-node models. Default flow demands were rebalanced (all switches ≈45 % util) so healthy nodes share one regime — before that, SW3 at 64 % util produced 60 % false positives.
- **Severity anchor.** Isolation Forest decision values bottom out near −0.115; severity 100 is anchored to a worst-case feature vector so the scale spans what the model can express.
- **Restart physics.** `FaultInjector.on_node_restart()` clears `node_overload` faults (a restart kills the runaway process). This is simulation physics, not label reading.
- **Escalation.** When the planner's simulated reroute leaves flows without an alternative (e.g. core router R1, link GW–R1) the plan is ESCALATE and the incident FAILS honestly.
- **Incident history survives reset**; only the active incident is cancelled.
- **Bash tool quirk (dev environment):** heredoc commands over ~7 KB fail with "unexpected EOF"; write large files with the Write tool.

## API Endpoints

- `GET /api/health`
- `GET /api/network/topology`, `GET /api/network/status`
- `GET /api/telemetry/current`, `GET /api/telemetry/history?limit=`
- `GET /api/faults`, `POST /api/faults/inject`, `POST /api/faults/reset`, `DELETE /api/faults/{id}`
- `GET /api/detection/current`, `GET /api/detection/model`
- `GET /api/diagnosis/current`
- `GET /api/incidents`, `GET /api/incidents/active`, `GET /api/incidents/{id}`
- `POST /api/healing/{incident_id}/execute`, `GET/POST /api/healing/mode`
- `WS /ws/network`
- Planned: `POST /api/demo/run`

## Data Models

Pydantic (`backend/app/models/`): `network.py` (NodeSchema, LinkSchema, FlowSchema, RouteSchema, TopologyResponse), `telemetry.py` (NodeTelemetry, LinkTelemetry, FlowTelemetry, NetworkSummary, TelemetrySnapshot, MetricPoint), `faults.py` (FaultType, Severity, ActiveFaultSchema, InjectFaultRequest), `detection.py` (ComponentAnomaly, MetricDeviation, DetectionResult), `diagnosis.py` (RootCause, ActionType, Hypothesis, RuleCheck, RemediationPlan, Diagnosis), `incident.py` (IncidentStatus, Incident, IncidentEvent, HealingActionRecord, RouteChange, MetricWindow, RecoveryCheck, RecoveryReport, IncidentMetrics, IncidentSummary). Frontend mirrors in `frontend/lib/types.ts` (incident/diagnosis types still to add).

## Fault Types

`router_congestion` (router/gateway), `link_failure` (link), `packet_loss_spike` (link), `bandwidth_degradation` (link), `node_overload` (any node), `traffic_spike` (switch), `router_failure` (router/switch). Severity low/medium/high scales effects (`backend/app/simulation/faults.py`).

## Detection

See Architecture → ML. Retrain with `cd backend && python ../scripts/train_detector.py`. Zero false positives over 200 healthy ticks; every fault detected on the first tick.

## Root Cause Analysis

Hypotheses: router_congestion, node_overload, traffic_spike, node_failure (nodes); link_failure, packet_loss_spike, bandwidth_saturation (links). Evidence = detector baseline deviations + strong symptoms + neighbour context + impacted flows. Plans: reroute_around_node, reroute_around_link, isolate_link, restart_node, rate_limit_source, escalate, monitor.

## Healing

See Architecture → Healing. Verified end to end: all seven healable scenarios resolve in 9 ticks (~13.5 s) after detection.

## AI Integration

Not implemented yet (Phase 9).

## Frontend

Done: `dashboard.tsx`, `top-bar.tsx`, `summary-cards.tsx`, `status-pill.tsx`, `topology/{topology-view,network-node,link-edge}.tsx`, `metrics-panel.tsx`, `fault-injector.tsx`, `hooks/use-network-socket.ts`, `lib/{api,config,status,types}.ts`. Pending: diagnosis panel, healing panel, incident timeline/history, affected-node highlight (`affectedIds` is currently an empty set).

## Testing

`cd backend && pytest` — 78 tests: routing, telemetry, health score, faults (+API), detection (+API), RCA (+API), healing/verification/incidents (+API), WebSocket. Full suite ≈10 s (first run trains the model).

## Environment Variables

See `.env.example`. Names only: `NETMEDIC_HOST`, `NETMEDIC_PORT`, `NETMEDIC_LOG_LEVEL`, `NETMEDIC_TICK_SECONDS`, `NETMEDIC_AUTO_TICK`, `NETMEDIC_DATABASE_URL`, `NETMEDIC_CORS_ORIGINS`, `NETMEDIC_AI_PROVIDER`, `QUALCOMM_AI_BASE_URL`, `QUALCOMM_AI_API_KEY`, `QUALCOMM_AI_MODEL`, `QUALCOMM_AI_TIMEOUT_SECONDS`, `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_WS_URL`.

## Commands

```bash
# Backend (Windows paths; use source .venv/bin/activate on macOS/Linux)
cd backend && python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev        # http://localhost:3000
npm run build && npm run lint && npx tsc --noEmit

# Tests
cd backend && pytest

# Retrain detector
cd backend && python ../scripts/train_detector.py [--save-dataset]

# Docker (pending Phase 12)
docker compose up --build
```

## Known Issues

- No persistence yet: incidents live in memory until Phase 10.
- Frontend does not yet render diagnosis / healing / incident state (backend delivers it in the WS message).
- `next dev` regenerates `frontend/AGENTS.md`/`CLAUDE.md`; keep them committed.

## Demo Procedure

Backend + frontend running → dashboard healthy → Fault injector: Target R4, Router congestion, Medium → Inject. Backend log shows [DETECTION] → [DIAGNOSIS] → [HEALING] reroutes F3/F4/F5 via R3 → [VERIFY] RESOLVED (~15 s). Topology shows rerouted (aqua) routes and R4 isolated. Reset restores everything. (UI panels for the incident arrive with the next frontend phase; `GET /api/incidents` shows the record meanwhile.)

## Last Major Change

- **Date:** 2026-09-21
- **Description:** Phases 4–8 complete — fault injection, Isolation Forest detection, RCA, self-healing, verification and incident state machine all working end to end on the backend.
- **Commit:** 6cb3b21
