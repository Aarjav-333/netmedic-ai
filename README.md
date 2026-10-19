# NetMedic AI

**Autonomous Network Detection, Diagnosis & Self-Healing Platform**

| | |
|---|---|
| **Hackathon** | Infosys IGNITE ENGNEXT 2026 – Hack-AI-Thon |
| **Problem Statement** | NC-04 — Self-Healing Network Simulator |
| **Status** | Functional MVP — full Detect → Diagnose → Heal → Verify loop working end to end |

![NetMedic AI detecting, diagnosing, healing and verifying a router congestion fault](docs/screenshots/demo.gif)

*Unedited capture: congestion injected on R4, then detect → diagnose → heal → verify. Traffic reroutes through R3 and recovery is confirmed against before/after telemetry — about 14 seconds end to end.*

---

## Overview

NetMedic AI is a functional, AI-assisted network simulator that continuously monitors
telemetry from a simulated campus network, detects degradation or failures with an
Isolation Forest, works out the most probable root cause with an explainable rule engine,
**changes the simulated network** to fix it (reroute, isolate, restart, rate-limit) and
then **verifies** — with before/after telemetry windows — that the network really recovered.

```
MONITOR → DETECT → DIAGNOSE → DECIDE → HEAL → VERIFY
```

It is deliberately **not** an LLM chatbot. Network state, telemetry, anomaly detection,
root-cause analysis, rerouting and recovery verification are all programmatic
(NetworkX + scikit-learn + deterministic scoring). The GenAI layer only turns the
structured diagnosis into an operator-friendly explanation, and the system keeps working
without it.

## Problem

Modern campus/enterprise networks degrade in ways that take operators minutes to notice
and longer to diagnose. Most monitoring stops at "alert fired". NC-04 asks for a
simulator that closes the loop: detect the fault, work out *why*, fix it, and prove it is
fixed — visibly and in real time.

## What the demo shows (≈14 s, measured)

1. A healthy 10-node campus network with animated active routes.
2. **Router R4 → Congestion → Inject Fault** (or **Run demo**).
3. R4's latency, loss and CPU climb; the Isolation Forest confirms the anomaly on the next tick.
4. The root-cause engine identifies *Router congestion on R4* with evidence and a 70-75 % confidence whose formula is printed.
5. The planner simulates a reroute, confirms every affected flow has an alternative path, and the healing engine raises R4's routing cost and recomputes Dijkstra paths — Hostel and Admin traffic now flows through R3 (highlighted on the topology).
6. After a settle period the verifier compares windows — a representative run: latency 207 ms → 21 ms, loss 14.6 % → 0.6 %, health 74 → 99, all four checks passed — **NETWORK RECOVERED**.
7. The incident, its timeline, actions and recovery report are stored in SQLite and listed in the history table.

![Incident in progress](docs/screenshots/incident-in-progress.png)

## Key Features

- **Physics-based simulator** — node load is derived from the routing table, so a reroute genuinely changes utilisation, queueing latency, loss and CPU on every node.
- **Seven fault types** with severity: router congestion, link failure, packet-loss spike, bandwidth degradation, node overload, traffic spike, complete router failure.
- **Ground-truth isolation** — the fault injector exposes only physical effects; detection, RCA and healing never see fault labels (enforced by tests).
- **ML detection** — Isolation Forest on baseline-normalised features, zero false positives over 200 healthy ticks, every fault detected on the first tick, 2-tick confirmation against flapping.
- **Explainable RCA** — weighted soft rules per hypothesis; the confidence *is* the rule-match score discounted by the runner-up, and the formula is shown in the UI.
- **Real self-healing** — reroute around node/link, isolate link, restart node (with traffic moved off meanwhile), rate-limit a bursting source; quarantine with hold-down timers; automatic restoration of primary routes once telemetry stays clean.
- **Mandatory verification** — baseline / before / after windows and four explicit checks → RESOLVED, PARTIALLY_RESOLVED or FAILED, with time-to-detect / diagnose / remediate / recover metrics.
- **Honest escalation** — if no alternative path exists (core router R1, uplink GW–R1) the plan is ESCALATE and the incident fails visibly instead of pretending.
- **Live dashboard** — React Flow topology, stat tiles, incident pipeline stepper, diagnosis + AI explanation, healing + verification report, timeline, history, small-multiple charts, manual-approval mode.
- **Demo mode** that drives the *real* pipeline for four scenarios.

## Architecture

```mermaid
flowchart TD
    FI[Fault Injector<br/>physical effects only] -. mutates .-> SIM
    SIM[Network Simulator<br/>NetworkX topology · static routing table] --> TEL[Telemetry Generator<br/>load → queueing → latency / loss / CPU]
    TEL --> DET[Anomaly Detection<br/>Isolation Forest + link/flow rules]
    DET --> RCA[Root Cause Analysis<br/>weighted soft rules · planner]
    RCA --> IM[Incident State Machine<br/>DETECTED → … → RESOLVED]
    IM --> HEAL[Self-Healing Engine<br/>reroute · isolate · restart · rate-limit]
    HEAL --> SIM
    IM --> VER[Recovery Verification<br/>baseline / before / after windows]
    IM --> AI[AI Explanation<br/>Mock / OpenAI-compatible]
    DET -.compiled + profiled.-> EDGE[Qualcomm AI Hub<br/>on-device detector · 42 us on NPU]
    IM --> DB[(SQLite<br/>incidents · actions · events · snapshots)]
    TEL & DET & RCA & IM --> WS[/WebSocket /ws/network — full state every tick/]
    WS --> UI[Next.js Dashboard<br/>React Flow · Recharts · shadcn/ui]
```

One `SimulationEngine` runs a 1.5 s tick loop. Each tick: fault expiry → healing housekeeping
(restarts, auto-restore) → fault effects → telemetry → detection → RCA → incident state machine →
persistence → broadcast. The incident machine advances one stage per tick so every transition is
visible: `DETECTED → ANALYZING → DIAGNOSED → REMEDIATING → VERIFYING → RESOLVED | PARTIALLY_RESOLVED | FAILED`.

### Topology

```
                 GW  (Internet Gateway)
                  |
                 R1  (Core Router) ─── SRV (Campus Server)
              /   |   \
            R2 ─ R3 ─ R4            distribution routers with lateral links
            |  \/ |  \/ |  \
          SW1  SW2  SW3  SW4        access switches, each dual-homed (primary + backup uplink)
```

Six traffic flows (Academic/Library/Hostel/Admin → Internet, Hostel/Academic → Server) ride
Dijkstra shortest paths. Routing weight = base latency + congestion penalty + loss penalty +
healing penalties; DOWN nodes/links are excluded.

### Network health score (0–100)

```
component score = 100 × (1 − max over metrics of clamp((value − ok) / (bad − ok), 0, 1))
health          = 0.45 × mean(flow scores) + 0.35 × mean(node scores) + 0.20 × mean(link scores)
```

Thresholds live in `backend/app/telemetry/health.py`; the three sub-scores are shown on the
dashboard so the number is always explainable.

### Detection

- Features per node: latency / healthy RTT, packet loss, throughput / capacity, utilisation, CPU, memory, connections / expected.
- Training data: fault-free simulator runs (6 seeds × 400 ticks, per-flow demand jitter ± 35 %, diurnal swing ± 15 %).
- `IsolationForest(n_estimators=200, contamination=0.005)`; model persisted with joblib and trained automatically on first boot (10–20 s depending on the machine).
- Severity 0–100 is derived linearly from the decision function between the training threshold and a worst-case vector — it is **not a probability** and is labelled as such.

### Root cause & confidence

For every flagged component and applicable hypothesis (router congestion, node overload,
traffic spike, node failure, link failure, packet-loss spike, bandwidth saturation):

```
score(H)   = Σ weight_i × strength_i / Σ weight_i        strength = clamp((value − ok)/(bad − ok))
confidence = best × (0.6 + 0.4 × (1 − runner_up / best))
```

Evidence combines the detector's baseline deviations ("Latency increased from 25 ms to 230 ms (9.4×)"),
strong symptoms, neighbour context and impacted flows.

### Verification

Windows: baseline (5 samples before the anomaly), before (3 samples before remediation), after
(3 samples following a 2-sample settle). Checks: affected flows healthy · health ≥ 85 · latency ≤
1.5 × baseline + 10 ms · loss ≤ baseline + 1 %. All pass → RESOLVED; ≥ half or +10 health → PARTIALLY_RESOLVED; else FAILED.

## Running the detector on Qualcomm silicon

The pipeline scores telemetry with a scikit-learn Isolation Forest in the backend. A real
deployment would score it **on the network device itself**, so the loop closes without a
round trip to a server. Tree ensembles don't map onto an NPU, so the on-device variant is a
compact autoencoder trained on the *same* seven normalised features and the *same* synthetic
healthy telemetry, flagging a sample when reconstruction error exceeds a threshold calibrated
on healthy data.

`scripts/edge_detector.py` trains it, **refuses to deploy unless it detects every injectable
fault**, then compiles and profiles it on real hardware through Qualcomm AI Hub:

| | |
|---|---|
| Device | Samsung Galaxy S25 (Family), TFLite |
| Model | 7-16-3-16-7 autoencoder, 362 parameters |
| Inference | **42 us** |
| Compute units | **4/4 layers on NPU** |
| Validation | detects every injected fault, 0 % false positives on 400 healthy samples, agrees with the Isolation Forest on every case |

```bash
pip install -r backend/requirements-edge.txt
export QUALCOMM_AI_HUB_TOKEN=...             # never commit it
python scripts/edge_detector.py              # train, validate, compile, profile
python scripts/edge_detector.py --offline    # train + validate only
```

The result is written to `backend/data/edge_profile.json`, served at `GET /api/detection/edge`
and shown on the dashboard with links to the actual compile and profile jobs. The backend
never imports torch and never calls AI Hub at runtime - it serves a recorded artefact, so
nothing on that card is computed or estimated in the app.

> **On the GenAI layer.** Qualcomm AI Hub optimises and profiles models for on-device
> deployment; it does not expose a hosted LLM. The explanation layer therefore runs on
> `MockProvider` by default, and `QualcommProvider` will drive any OpenAI-compatible
> chat-completions endpoint the moment one is supplied - three env vars, no code change.

## Technology Stack

**Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui, React Flow (`@xyflow/react`), Recharts
**Backend:** Python 3.11, FastAPI, Pydantic v2, Uvicorn, WebSockets
**Simulation & ML:** NetworkX, NumPy, Pandas, scikit-learn (Isolation Forest), joblib
**Database:** SQLite via SQLAlchemy 2
**Qualcomm:** AI Hub compiles and profiles the on-device detector on real Snapdragon hardware (`scripts/edge_detector.py`)
**GenAI:** `AIExplanationProvider` abstraction — `MockProvider` (default) and `QualcommProvider` for any OpenAI-compatible endpoint, configured only through environment variables
**Ops:** Docker, Docker Compose, GitHub

## Screenshots

| Healthy network | Incident in progress | Incident resolved |
|---|---|---|
| ![healthy](docs/screenshots/healthy-network.png) | ![progress](docs/screenshots/incident-in-progress.png) | ![resolved](docs/screenshots/incident-resolved.png) |

Telemetry is deliberately unseeded in normal runs, so exact figures move a little between runs; set `NETMEDIC_RANDOM_SEED` to make a run reproducible.

## Setup

### Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- (optional) Docker Desktop

### Environment variables

Copy `.env.example` to `.env` and adjust if needed. Defaults work out of the box. Never commit `.env`.

| Variable | Purpose |
|---|---|
| `NETMEDIC_TICK_SECONDS` | telemetry/pipeline tick (default 1.5) |
| `NETMEDIC_DATABASE_URL` | SQLite URL (default `sqlite:///./data/netmedic.db`, relative to `backend/`) |
| `BACKEND_PORT` / `FRONTEND_PORT` | host ports used by `docker compose` (default 8000 / 3000) |
| `NETMEDIC_CORS_ORIGINS` / `NETMEDIC_CORS_ORIGIN_REGEX` | allowed dashboard origins, applied to REST **and** the WebSocket handshake. Backend default: loopback only. Compose additionally allows private/`.local` hosts on the dashboard port for LAN demos — the API has no auth, so never widen this to any host |
| `NETMEDIC_AI_PROVIDER` | `mock` (default) or `qualcomm` |
| `QUALCOMM_AI_HUB_TOKEN` | Qualcomm AI Hub token, build-time only — used by `scripts/edge_detector.py` to compile/profile the on-device detector. The backend never reads it |
| `QUALCOMM_AI_BASE_URL` / `QUALCOMM_AI_API_KEY` / `QUALCOMM_AI_MODEL` | An OpenAI-compatible chat-completions endpoint for the explanation layer (see `backend/app/ai/qualcomm.py` for the documented request shape) |
| `NEXT_PUBLIC_API_BASE_URL` / `NEXT_PUBLIC_WS_URL` | optional overrides; by default the browser derives the backend address from its own location and the backend port at runtime |

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

First start trains the Isolation Forest (10–20 s depending on the machine) and writes `backend/data/models/`. Retrain any time with
`python ../scripts/train_detector.py`. Interactive API docs: http://localhost:8000/docs.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The dashboard derives the backend address from its own location and port 8000; if the backend runs elsewhere, set `NETMEDIC_BACKEND_PORT=8010` (or `NEXT_PUBLIC_API_BASE_URL` / `NEXT_PUBLIC_WS_URL`) in `frontend/.env.local`. Use Node 20 / npm 10 (`.nvmrc`, `packageManager` — run `corepack enable` once and npm picks the pinned version) so `package-lock.json` stays identical to what the Docker image installs; if you must use another npm and Docker's `npm ci` later complains about the lockfile, regenerate it in Linux:
`docker run --rm -v "${PWD}:/app" -w /app node:20-alpine npm install --package-lock-only`.

### Tests

```bash
cd backend
pytest            # 90+ tests: routing, telemetry, faults, detection, RCA, healing, verification, incidents, AI, DB, demo
```

### Docker

```bash
docker compose up --build        # backend on :8000, dashboard on :3000
```

If those ports are taken, set `BACKEND_PORT` / `FRONTEND_PORT` in a project-root `.env` (Compose reads it on every platform; copy `.env.example`), or in the shell:

```powershell
$env:BACKEND_PORT = "8010"; $env:FRONTEND_PORT = "3010"; docker compose up --build   # PowerShell
```
```bash
BACKEND_PORT=8010 FRONTEND_PORT=3010 docker compose up --build                     # bash / zsh
```

Nothing host-specific is baked into the images: the frontend container tells the browser the backend port at runtime (`/api/config`), so changing ports never needs a rebuild and the dashboard works from `localhost`, `127.0.0.1` or a private LAN address alike (public hosts are refused — see the CORS note above). The backend trains the detector on first boot (10–20 s, covered by the healthcheck's `start_period`); the SQLite database and model live in the `netmedic-data` volume.

## Demo Workflow

1. Start backend and frontend — the topology renders healthy (health ≈ 100).
2. Either press **Run demo** (scenario *Router congestion on R4*) or choose **Target R4 → Router congestion → Medium → Inject fault**.
3. Watch the **Incident pipeline** card step through Detect → Diagnose → Heal → Verify; R4 pulses on the topology.
4. **AI diagnosis** shows the root cause, evidence, confidence formula and the recommended action; **Self-healing** shows the alternative routes (F3/F4/F5 now via R3) and, ~8 s later, the before/after verification report.
5. Rerouted paths glow aqua on the topology; R4 is marked *Isolated*. Charts show R4's spike and the flows' recovery.
6. **Incident history** lists the incident with recovery and total durations. Press **Reset** to restore the primary routes.
7. Try the other scenarios (link failure, traffic spike, node overload) or switch **Auto-healing** off to approve remediations manually.

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | liveness |
| GET | `/api/network/topology` · `/api/network/status` | nodes, links, flows, routes |
| GET | `/api/telemetry/current` · `/api/telemetry/history?limit=` | latest snapshot / chart series |
| GET · POST · POST · DELETE | `/api/faults` · `/api/faults/inject` · `/api/faults/reset` · `/api/faults/{id}` | fault injection |
| GET | `/api/detection/current` · `/api/detection/model` | anomalies / model metadata |
| GET | `/api/diagnosis/current` | live root-cause analysis |
| GET | `/api/incidents` · `/api/incidents/active` · `/api/incidents/{id}` | incident records |
| POST · GET/POST | `/api/healing/{incident_id}/execute` · `/api/healing/mode` | manual approval / auto-heal toggle |
| GET · POST | `/api/ai/provider` · `/api/ai/explain/{incident_id}` | AI explanation |
| GET · POST | `/api/demo/scenarios` · `/api/demo/run` · `/api/demo/stop` · `/api/demo/status` | demo mode |
| WS | `/ws/network` | full state every tick |

## Repository Structure

```
netmedic-ai/
├── frontend/                 Next.js dashboard
│   ├── app/                  layout + page
│   ├── components/dashboard/ topology, panels, charts, fault injector, demo control
│   ├── hooks/                WebSocket hook
│   └── lib/                  API client, types, status helpers
├── backend/
│   ├── app/
│   │   ├── api/              REST + WebSocket routers
│   │   ├── simulation/       topology, routing, network state, faults, effects
│   │   ├── telemetry/        generator + health score
│   │   ├── detection/        features, trainer, Isolation Forest detector
│   │   ├── diagnosis/        rules, RCA, remediation planner
│   │   ├── healing/          healing engine + recovery verifier
│   │   ├── incidents/        incident state machine
│   │   ├── ai/               explanation providers (mock, Qualcomm)
│   │   ├── database/         SQLAlchemy models + repository
│   │   ├── models/           Pydantic schemas
│   │   ├── engine.py         tick loop orchestrator
│   │   └── demo.py           demo scenarios
│   ├── tests/
│   └── requirements.txt
├── docs/                     screenshots, architecture notes
├── scripts/train_detector.py
├── CONTEXT.md                persistent project memory for AI sessions
├── docker-compose.yml
└── .env.example
```

## Future Improvements

- Multi-incident correlation and cascading-failure diagnosis
- Additional detectors (per-node models, seasonal baselines, autoencoders) and online retraining
- Policy engine with approval thresholds by risk level
- Topologies loaded from YAML and larger multi-site graphs
- Exportable incident reports (PDF / Markdown)

## License

MIT
