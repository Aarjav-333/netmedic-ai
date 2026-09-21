# NetMedic AI — Presenter's demo script

Target length: 3–4 minutes. Everything below is driven by the real pipeline; nothing is scripted in the UI.

## Before the session

1. `cd backend && .venv\Scripts\activate && uvicorn app.main:app --port 8000` — wait for `[ENGINE] Tick loop started`.
2. `cd frontend && npm run dev` — open http://localhost:3000, check the top-right pill says **Live**.
3. Press **Reset** once so the topology shows primary routes and health ≈ 100.
4. Keep the backend terminal visible on a second screen: the `[DETECTION] / [DIAGNOSIS] / [HEALING] / [VERIFY]` lines are part of the story.

## Script

**0:00 — Healthy network.** "Ten-node campus network, six traffic flows on primary paths. Telemetry every 1.5 s: latency, loss, throughput, CPU, memory, connections. Health score 100 — the formula is documented, not random."

**0:20 — Inject.** Fault injector: Target **R4 · Hostel Router**, Fault **Router congestion**, Severity **Medium**, **Inject fault**. "The injector only adds physical load to R4. Nothing downstream is told what we did."

**0:30 — Detect.** Point at R4 turning critical (≈230 ms, 15 % loss, 97 % CPU) and the pipeline card: **FAULT DETECTED**. "An Isolation Forest trained on synthetic healthy telemetry flags R4; we require two consecutive ticks so it never flaps."

**0:35 — Diagnose.** **ROOT CAUSE IDENTIFIED: Router congestion on R4, confidence ≈ 72 %.** Read two evidence lines and the confidence sentence: "Rule-match score 0.97, runner-up 0.61 — the confidence is the rule score discounted by the competing hypothesis. No invented numbers." Scroll to the AI explanation: "The LLM layer only narrates the structured diagnosis; with Qualcomm credentials it uses Qualcomm Cloud AI Playground, otherwise this deterministic mock."

**0:40 — Heal.** **AUTO-HEALING IN PROGRESS → TRAFFIC REROUTED.** On the topology the aqua routes move from R4 to R3; R4 shows *Isolated*. In the healing panel: "F3: SW3 › R4 › R1 › GW → SW3 › R3 › R1 › GW. The routing table actually changed — the simulator recomputed Dijkstra with R4 penalised."

**0:45 — Verify.** **VERIFYING RECOVERY** — "we wait two samples to settle, then average three." Then **NETWORK RECOVERED** with the before/after table: latency 215 → 20 ms, loss 15.5 → 0.7 %, health 74 → 99, four checks passed. "Resolved means measured, not assumed."

**1:15 — Persistence.** Incident history row with recovery/total times; click it to reopen the record after a **Reset**.

**1:30 — Variety (optional).** Run demo → *Link failure R4-SW3* (isolate + backup uplink) or *Node overload on R2* (restart with traffic moved off, then primary routes restored). Show *Router congestion on R1* by hand to demonstrate honest escalation: no alternative path → ESCALATE → FAILED.

**2:30 — Manual mode (optional).** Toggle **Auto-healing** off, inject again, and approve the recommendation with **Execute** in the healing panel.

## If something goes wrong

- Dashboard says *Backend offline*: restart uvicorn; the WebSocket reconnects automatically.
- An old incident is still active: press **Reset** (cancels it, clears faults and healing state).
- Model retrain wanted: `cd backend && python ../scripts/train_detector.py`.
