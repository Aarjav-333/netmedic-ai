"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getBackendConfig } from "@/lib/config";
import type { MetricPoint, StateMessage, TelemetrySnapshot } from "@/lib/types";

export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "offline";

const HISTORY_LENGTH = 120;
const MAX_BACKOFF_MS = 8000;

function toMetricPoint(snapshot: TelemetrySnapshot): MetricPoint {
  const latency: Record<string, number> = {};
  const cpu: Record<string, number> = {};
  const util: Record<string, number> = {};
  const loss: Record<string, number> = {};
  for (const n of snapshot.nodes) {
    latency[n.node_id] = n.latency_ms;
    cpu[n.node_id] = n.cpu_percent;
    util[n.node_id] = n.bandwidth_utilization_percent;
    loss[n.node_id] = n.packet_loss_percent;
  }
  return {
    tick: snapshot.tick,
    timestamp: snapshot.timestamp,
    health_score: snapshot.summary.health_score,
    avg_latency_ms: snapshot.summary.avg_latency_ms,
    avg_packet_loss_percent: snapshot.summary.avg_packet_loss_percent,
    total_throughput_mbps: snapshot.summary.total_throughput_mbps,
    node_latency_ms: latency,
    node_cpu_percent: cpu,
    node_utilization_percent: util,
    node_packet_loss_percent: loss,
  };
}

/**
 * Subscribes to the backend state stream. Reconnects with backoff, backfills
 * chart history from the REST API on (re)connect, and keeps a rolling window
 * of metric points for the charts.
 */
export function useNetworkSocket() {
  const [state, setState] = useState<StateMessage | null>(null);
  const [history, setHistory] = useState<MetricPoint[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const attemptRef = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);
  const closedRef = useRef(false);

  const backfill = useCallback(async () => {
    try {
      const { apiBaseUrl } = await getBackendConfig();
      const res = await fetch(`${apiBaseUrl}/api/telemetry/history?limit=${HISTORY_LENGTH}`, {
        cache: "no-store",
      });
      if (!res.ok) return;
      const body = (await res.json()) as { points: MetricPoint[] };
      setHistory((current) => {
        const seen = new Set(body.points.map((p) => p.tick));
        const merged = [...body.points, ...current.filter((p) => !seen.has(p.tick))];
        merged.sort((a, b) => a.tick - b.tick);
        return merged.slice(-HISTORY_LENGTH);
      });
    } catch {
      /* backend not reachable yet; the socket retry will cover it */
    }
  }, []);

  useEffect(() => {
    closedRef.current = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = async () => {
      if (closedRef.current) return;
      setStatus(attemptRef.current === 0 ? "connecting" : "reconnecting");
      const { wsUrl } = await getBackendConfig();
      if (closedRef.current) return;
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setStatus("connected");
        void backfill();
      };

      ws.onmessage = (event) => {
        let message: StateMessage;
        try {
          message = JSON.parse(event.data as string) as StateMessage;
        } catch {
          return;
        }
        if (message.type !== "state") return;
        setState(message);
        if (message.telemetry) {
          const point = toMetricPoint(message.telemetry);
          setHistory((current) => {
            if (current.length && current[current.length - 1].tick >= point.tick) return current;
            return [...current, point].slice(-HISTORY_LENGTH);
          });
        }
      };

      ws.onclose = () => {
        socketRef.current = null;
        if (closedRef.current) return;
        attemptRef.current += 1;
        setStatus("offline");
        const delay = Math.min(MAX_BACKOFF_MS, 500 * 2 ** Math.min(attemptRef.current, 4));
        retryTimer = setTimeout(() => void connect(), delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    void connect();

    return () => {
      closedRef.current = true;
      if (retryTimer) clearTimeout(retryTimer);
      socketRef.current?.close();
    };
  }, [backfill]);

  /** Reset chart history (e.g. after the simulation is reset). */
  const clearHistory = useCallback(() => setHistory([]), []);

  return { state, history, status, clearHistory, refreshHistory: backfill };
}
