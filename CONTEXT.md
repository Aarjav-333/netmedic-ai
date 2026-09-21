# NetMedic AI — Project Context

> Persistent project memory. Read this first in every new AI session. Update after every major change.

## Project

- **Name:** NetMedic AI — Autonomous Network Detection, Diagnosis & Self-Healing Platform
- **Hackathon:** Infosys IGNITE ENGNEXT 2026 – Hack-AI-Thon
- **Problem statement:** NC-04 — Self-Healing Network Simulator
- **Objective:** Functional MVP that continuously monitors a simulated network, detects degradation, diagnoses the root cause from telemetry (never from injected fault labels), executes a real corrective action on the simulated graph (rerouting is the primary one), and verifies recovery. Lifecycle: MONITOR → DETECT → DIAGNOSE → DECIDE → HEAL → VERIFY.

## Current Architecture

- **Frontend:** Next.js (App Router) + React + TypeScript + Tailwind CSS + shadcn/ui; React Flow for topology; Recharts for metrics. Consumes REST + WebSocket only — renders backend state, never simulates locally.
- **Backend:** Python 3.11, FastAPI, Pydantic v2, Uvicorn. A single `SimulationEngine` singleton runs a background asyncio tick loop (~1.5 s). Each tick: telemetry → detection → RCA → incident state machine → healing → verification → persistence → WebSocket broadcast.
- **Network simulator:** NetworkX graph (~10 nodes). Dijkstra routing with weight = base_latency + congestion_penalty + packet_loss_penalty + healing_penalty.
- **ML:** scikit-learn Isolation Forest trained on synthetic healthy telemetry; model persisted with joblib.
- **AI provider:** `AIExplanationProvider` abstraction with `MockProvider` (default) and `QualcommProvider` (fully env-driven; no hardcoded endpoints).
- **Database:** SQLite via SQLAlchemy (incidents, healing actions, incident events, telemetry snapshots).
- **WebSocket:** `/ws/network` pushes a full `NetworkSnapshot` every tick (topology state, telemetry, active routes, incidents, health score).

## Current Repository

- **GitHub:** https://github.com/Aarjav-333/netmedic-ai (public)
- **Branch:** `main`
- **Important directories:** `backend/app/{api,simulation,telemetry,detection,diagnosis,healing,ai,database,models}`, `backend/tests`, `frontend/{app,components,lib,hooks}`, `docs`, `scripts`

## Current Project Status

Phase 0 complete — project initialised; starting Phase 1 (~5% complete).

## Completed

- Phase 0: public GitHub repo, README, CONTEXT, .gitignore, .env.example, LICENSE
- Backend skeleton: FastAPI app factory, pydantic-settings config (`app/config.py`), tagged logging, `GET /api/health`, pytest fixture + health test
- Frontend skeleton: Next.js 16.3 (App Router, TS, Tailwind v4), shadcn/ui v4 (radix base; `cn` from the `cn` package), `@xyflow/react` 12, `recharts` 3, typed `lib/api.ts` fetch helper, dark theme by default, landing page shows backend connection status

## In Progress

- Phase 1: NetworkX topology + routing + topology API

## Next Tasks

1. Phase 1 — NetworkX topology, node/link models, Dijkstra routing, topology API
2. Phase 2 — telemetry generator + WebSocket streaming
3. Phase 3 — dashboard base (React Flow topology, summary cards, charts)
4. Phase 4 — fault injection
5. Phase 5 — Isolation Forest detection
6. Phase 6 — root cause analysis
7. Phase 7 — self-healing (rerouting)
8. Phase 8 — recovery verification
9. Phase 9 — AI explanation provider
10. Phase 10 — SQLite incident management
11. Phase 11 — demo mode
12. Phase 12 — polish, Docker, docs

## Important Technical Decisions

- **Single engine, single tick loop.** All pipeline stages run in one deterministic loop so the UI always reflects consistent backend state. No stage reads the fault injector's ground-truth label.
- **Ground truth isolation.** `FaultInjector` stores the injected fault only for evaluation/debug; detection & RCA consume telemetry + topology only.
- **Qualcomm integration is env-driven.** No fabricated endpoints/SDKs. `QualcommProvider` requires `QUALCOMM_AI_BASE_URL`, `QUALCOMM_AI_API_KEY`, `QUALCOMM_AI_MODEL`; otherwise `MockProvider` produces deterministic narrative from structured RCA output.
- **Isolation Forest scores are not probabilities.** UI shows a 0–100 "anomaly severity" derived from the decision function, labelled as such.
- **Confidence comes from the RCA scoring engine** (rule match weights normalised), never arbitrary.

## API Endpoints

_Planned (Phase 1+):_
- `GET /api/health`
- `GET /api/network/topology`, `GET /api/network/status`
- `GET /api/telemetry/current`
- `POST /api/faults/inject`, `POST /api/faults/reset`
- `GET /api/incidents`, `GET /api/incidents/{id}`
- `POST /api/healing/{incident_id}/execute`
- `POST /api/demo/run`
- `WS /ws/network`

## Data Models

_To be documented as implemented._

## Fault Types

Planned: `router_congestion`, `link_failure`, `packet_loss_spike`, `bandwidth_degradation`, `node_overload`, `traffic_spike` (+ optional `router_failure`).

## Detection

Planned: Isolation Forest (scikit-learn) on per-node feature vectors.

## Root Cause Analysis

Planned: deterministic rule/scoring engine with neighbour context.

## Healing

Planned: reroute (penalise node / isolate link → recompute Dijkstra), load redistribution, simulated restart.

## AI Integration

Not yet implemented. Provider abstraction planned for Phase 9.

## Frontend

Not yet implemented.

## Testing

Not yet implemented. Planned: pytest unit tests + integration test of full pipeline.

## Environment Variables

See `.env.example`. Names only:
`NETMEDIC_HOST`, `NETMEDIC_PORT`, `NETMEDIC_LOG_LEVEL`, `NETMEDIC_TICK_SECONDS`, `NETMEDIC_DATABASE_URL`, `NETMEDIC_CORS_ORIGINS`, `NETMEDIC_AI_PROVIDER`, `QUALCOMM_AI_BASE_URL`, `QUALCOMM_AI_API_KEY`, `QUALCOMM_AI_MODEL`, `QUALCOMM_AI_TIMEOUT_SECONDS`, `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_WS_URL`.

## Commands

```bash
# Backend
cd backend && python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Tests
cd backend && pytest

# Docker
docker compose up --build
```

## Known Issues

- Frontend toolchain notes: Next.js 16 ships its own docs in `frontend/node_modules/next/dist/docs/` — consult before using unfamiliar APIs. `create-next-app` generated `frontend/AGENTS.md`/`CLAUDE.md`; keep them committed (next dev regenerates them).

## Demo Procedure

Not yet available (Phase 11).

## Last Major Change

- **Date:** 2026-09-21
- **Description:** Phase 0 complete — backend + frontend scaffolds build and run together.
- **Commit:** db41bd8
