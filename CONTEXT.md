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
- **ML:** scikit-learn Isolation Forest on 7 baseline-normalised node features (`backend/app/detection/features.py`), trained on synthetic fault-free runs (6 seeds × 400 ticks, per-flow demand jitter + diurnal swing). Persisted to `backend/data/models/isolation_forest.joblib` (+ `.json` metadata), auto-trained on first boot (10–20 s depending on the machine). Links/flows use rules. 2-tick confirmation. Severity 0–100 = linear from the decision threshold to the model's worst-case score (documented as *not* a probability).
- **RCA:** deterministic hypothesis scoring (`backend/app/diagnosis/rules.py`): weighted soft rules per (component, hypothesis); confidence = best_score × (0.6 + 0.4 × (1 − runner_up/best)); formula spelled out in each diagnosis. Planner simulates reroutes before recommending; escalates when no alternative path exists.
- **Healing:** `HealingEngine` mutates real simulator state (penalties + route recompute, link isolation, node restart, rate limits). Quarantine with hold-down (restore after 6 clean ticks & ≥10-tick hold; 60-tick hold if flapping).
- **Verification:** windows of averaged samples (baseline 5 pre-anomaly, before 3, after 3 following a 2-tick settle). Four explicit checks → RESOLVED / PARTIALLY_RESOLVED / FAILED.
- **Incidents:** `IncidentManager` state machine advances one stage per tick: DETECTED → ANALYZING → DIAGNOSED → REMEDIATING → VERIFYING → RESOLVED/PARTIALLY_RESOLVED/FAILED (+ CANCELLED on reset or when a transient anomaly clears before diagnosis). One active incident at a time. Guard: an incident opens only for confirmed node/link anomalies with severity ≥ 20 or ≥ 4 consecutive ticks (prevents false-positive incidents on long healthy runs).
- **AI provider:** `backend/app/ai/` — `AIExplanationProvider` with `MockProvider` (default, deterministic narrative from the structured diagnosis) and `QualcommProvider` (env-driven; OpenAI-style chat-completions request shape is a documented assumption; falls back to mock on any error, flagged `fallback=true`). Called asynchronously when an incident reaches DIAGNOSED; result in `Incident.ai_explanation`.
- **Database:** SQLite via SQLAlchemy (`backend/app/database/`): `incidents` (indexed columns + full JSON payload), `healing_actions`, `incident_events`, `telemetry_snapshots` (one summary every 10 ticks, pruned to 2000 rows). Incident history reloaded on boot. Tests use `backend/data/netmedic_test.db`.
- **Demo mode:** `backend/app/demo.py` `DemoRunner` — reset → 5 s healthy → inject scenario → wait for the real pipeline to close the incident. Scenarios: congestion (R4), link_failure (L-R4-SW3), traffic_spike (SW3), overload (R2).
- **WebSocket:** `/ws/network` pushes the full state message every tick: `{type, tick, topology, telemetry, faults, detection, diagnosis, incident, incidents, quarantined, auto_heal, demo}`.
- **Backend address resolution (frontend):** nothing host-specific is baked into the bundle. `frontend/lib/config.ts` resolves once per page load: build-time `NEXT_PUBLIC_*` override → runtime `GET /api/config` (Next route handler reading `NETMEDIC_BACKEND_PORT` / `NETMEDIC_API_BASE_URL` / `NETMEDIC_WS_URL` from the frontend server's env) → derive from `window.location` + port 8000; the WS URL, unless given explicitly, is derived from the resolved API URL. A failed `/api/config` fetch is not cached (the socket retry re-resolves). Compose passes `NETMEDIC_BACKEND_PORT=${BACKEND_PORT}` at runtime, so port changes need no rebuild. Backend CORS: exact origins + `NETMEDIC_CORS_ORIGIN_REGEX` (full-matched; compose default `^https?://[^/]+:<FRONTEND_PORT>`), `allow_credentials=False`. `.env.example` leaves the CORS vars commented out so compose can derive them from `FRONTEND_PORT`.

## Current Repository

- **GitHub:** https://github.com/Aarjav-333/netmedic-ai (public)
- **Branch:** `main`
- **Backend modules:** `backend/app/{api,simulation,telemetry,detection,diagnosis,healing,incidents,ai,database,models}`; tests in `backend/tests`
- **Frontend:** `frontend/{app,components/dashboard,components/ui,hooks,lib}`
- **Scripts:** `scripts/train_detector.py`

## Current Project Status

All phases 0–12 implemented and verified, including the Docker stack (both images build; demo resolves inside the containers). ~98% complete — only optional polish and the real Qualcomm credentials remain.

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
- Phase 9: AI explanation providers + `GET /api/ai/provider`, `POST /api/ai/explain/{id}`
- Phase 10: SQLite persistence (incidents, actions, events, snapshots) with reload on boot
- Frontend incident UI: pipeline stepper card, AI diagnosis panel, self-healing panel (routes, verification report, manual approval), timeline, history table, auto-heal toggle, affected-node highlight, demo control
- Phase 11: demo mode (4 scenarios) + `/api/demo/*`
- Phase 12: Dockerfiles + docker-compose + standalone Next build, README rewrite with screenshots/formulas/API table, `docs/demo-script.md`, transient-anomaly guard

## In Progress

- Nothing active.

## Next Tasks

1. Optional: obtain Qualcomm Cloud AI Playground credentials from the team, set `NETMEDIC_AI_PROVIDER=qualcomm` + `QUALCOMM_AI_*`, confirm the request shape in `backend/app/ai/qualcomm.py` against the real API.
2. Optional polish: mobile layout pass, keyboard focus states, README screenshot refresh after any UI change.
3. Optional: rehearse with `docs/demo-script.md`; consider recording a GIF for the README.

## Important Technical Decisions

- **Single engine, single tick loop** so the UI always reflects consistent backend state.
- **Ground truth isolation.** `FaultInjector.effects()` exposes only physics (extra load, capacity multiplier, loss adds…). Detection/RCA/healing never import fault labels. Tests assert no fault vocabulary leaks into detection output.
- **Static routing table.** Routes only change when the healing engine recomputes them, which is what makes rerouting a genuine remediation. Link/node failure black-holes flows until healed.
- **One global Isolation Forest on normalised features** (latency/base RTT, loss, throughput/capacity, utilisation, CPU, memory, connections/expected) instead of per-node models. Default flow demands were rebalanced (all switches ≈45 % util) so healthy nodes share one regime — before that, SW3 at 64 % util produced 60 % false positives.
- **Severity anchor.** Isolation Forest decision values bottom out near −0.115; severity 100 is anchored to a worst-case feature vector so the scale spans what the model can express.
- **Restart physics.** `FaultInjector.on_node_restart()` clears `node_overload` faults (a restart kills the runaway process). This is simulation physics, not label reading.
- **Escalation.** When the planner's simulated reroute leaves flows without an alternative (e.g. core router R1, link GW–R1) the plan is ESCALATE and the incident FAILS honestly.
- **Incident history survives reset**; only the active incident is cancelled.
- **Transient guard.** After a ~5000-tick healthy run, one 2-tick severity-8 blip on R3 opened an incident that ended FAILED. Incidents now need severity ≥ 20 or 4 consecutive ticks; anomalies that clear before diagnosis close as CANCELLED.
- **Demo mode never scripts outcomes.** It only resets, waits, and injects; the pipeline decides the result and the fault stays active afterwards so the reroute remains visible. One side effect: `DemoRunner._run` forces `auto_heal = True` after the reset so the demo never blocks on manual approval, and nothing restores the operator's previous setting — if they had switched to Manual, it stays Armed until they toggle it back.
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
- `GET /api/ai/provider`, `POST /api/ai/explain/{incident_id}`
- `GET /api/demo/scenarios`, `GET /api/demo/status`, `POST /api/demo/run`, `POST /api/demo/stop`
- `WS /ws/network`

## Data Models

Pydantic (`backend/app/models/`): `network.py` (NodeSchema, LinkSchema, FlowSchema, RouteSchema, TopologyResponse), `telemetry.py` (NodeTelemetry, LinkTelemetry, FlowTelemetry, NetworkSummary, TelemetrySnapshot, MetricPoint), `faults.py` (FaultType, Severity, ActiveFaultSchema, InjectFaultRequest), `detection.py` (ComponentAnomaly, MetricDeviation, DetectionResult), `diagnosis.py` (RootCause, ActionType, Hypothesis, RuleCheck, RemediationPlan, Diagnosis), `incident.py` (IncidentStatus, Incident, IncidentEvent, HealingActionRecord, RouteChange, MetricWindow, RecoveryCheck, RecoveryReport, IncidentMetrics, IncidentSummary, HealingModeRequest, HealingModeResponse), `ai.py` (AIExplanation, AIProviderStatus). ORM tables in `backend/app/database/models.py`. Frontend mirrors in `frontend/lib/types.ts`.

## Fault Types

`router_congestion` (router/gateway), `link_failure` (link), `packet_loss_spike` (link), `bandwidth_degradation` (link), `node_overload` (any node), `traffic_spike` (switch), `router_failure` (router/switch). Severity low/medium/high scales effects (`backend/app/simulation/faults.py`).

## Detection

See Architecture → ML. Retrain with `cd backend && python ../scripts/train_detector.py`. Zero false positives over 200 healthy ticks; every fault detected on the first tick.

## Root Cause Analysis

Hypotheses: router_congestion, node_overload, traffic_spike, node_failure (nodes); link_failure, packet_loss_spike, bandwidth_saturation (links). Evidence = detector baseline deviations + strong symptoms + neighbour context + impacted flows. Plans: reroute_around_node, reroute_around_link, isolate_link, restart_node, rate_limit_source, escalate, monitor.

## Healing

See Architecture → Healing. Verified end to end: all seven healable scenarios resolve in 9 ticks (~13.5 s) after detection.

## AI Integration

Mock provider active by default. Qualcomm provider is fully env-driven (`QUALCOMM_AI_BASE_URL` = full chat/completions URL, `QUALCOMM_AI_API_KEY`, `QUALCOMM_AI_MODEL`); request/response shape assumption documented in `backend/app/ai/qualcomm.py` and must be checked against the real platform. Credentials have NOT been provided yet.

## Frontend

Components in `frontend/components/dashboard/`: `dashboard.tsx` (layout + incident selection), `top-bar.tsx` (status, auto-heal switch, connection), `summary-cards.tsx`, `status-pill.tsx`, `topology/{topology-view,network-node,link-edge}.tsx`, `incident-status.tsx` (stepper + big stage labels), `diagnosis-panel.tsx`, `healing-panel.tsx`, `incident-timeline.tsx`, `incident-history.tsx`, `metrics-panel.tsx`, `fault-injector.tsx`, `demo-control.tsx`; `hooks/use-network-socket.ts`; `lib/{api,config,status,types}.ts`. With no active incident the panels show the selected/most recent historical incident (fetched via `GET /api/incidents/{id}`).

## Testing

`cd backend && pytest` — 94 tests: CORS (exact + regex, no credentials), routing, telemetry, health score, faults (+API), detection (+API), RCA (+API), healing/verification/incidents (+API), AI providers (mock + mocked-HTTP Qualcomm), database round-trip, demo mode, WebSocket. Full suite ≈12 s (first run trains the model). Frontend: `npm run lint`, `npx tsc --noEmit`, `npm run build` all clean.

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

# Docker (verified 2026-09-21: images build, demo resolves in-container, port change without rebuild, 127.0.0.1 access)
docker compose up --build
# other ports: put BACKEND_PORT=8010 / FRONTEND_PORT=3010 in .env (or $env:BACKEND_PORT="8010" in PowerShell); no rebuild needed
```

## Known Issues

- Port 8000 on the dev machine is used by another project (SATVA) running in Docker. For the compose stack set `BACKEND_PORT`/`FRONTEND_PORT` in a project-root `.env` (or `$env:BACKEND_PORT=... ` in PowerShell); for local dev run uvicorn on another port and set `NETMEDIC_BACKEND_PORT` in `frontend/.env.local`.
- `frontend/package-lock.json` must stay complete for Linux. Toolchain is pinned to the image (`packageManager` npm@10.8.2, `.nvmrc` 20; run `corepack enable`). If another npm rewrites the lock and Docker's `npm ci` complains, regenerate inside `node:20-alpine` with `npm install --package-lock-only`.
- Qualcomm provider untested against the real API (no credentials); request shape is an assumption.
- No redundancy by design for the single-homed edges of the topology: core router R1, gateway GW (only link L-GW-R1), campus server SRV (only link L-R1-SRV), and those two links. Every flow terminates at GW (F1–F4) or SRV (F5–F6), so a fault on any of these strands flows, the planner returns ESCALATE, and the incident FAILS honestly.
- `next dev` regenerates `frontend/AGENTS.md`/`CLAUDE.md`; keep them committed.

## Demo Procedure

See `docs/demo-script.md`. Short version: backend + frontend running → dashboard healthy → **Run demo** (or Target R4 · Router congestion · Medium · Inject) → pipeline card walks Detect → Diagnose → Heal → Verify; F3/F4/F5 reroute via R3 (aqua), R4 isolated; verification table shows latency ≈215→20 ms, loss ≈15→0.7 %, health 74→99; NETWORK RECOVERED ≈13 s after injection; history row stored in SQLite. **Reset** restores primary routes.

## Last Major Change

- **Date:** 2026-09-21
- **Description:** Applied the ten findings of the xhigh code review of the Docker layer — runtime backend-URL resolution (`/api/config`), portable port overrides, loopback/LAN CORS, toolchain pin, compose/env/docs consistency. Verified: compose on 8010/3010 and then 8020/3020 without rebuild, dashboard via 127.0.0.1, local dev against port 8010.
- **Commit:** e6baadb
