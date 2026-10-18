"use client";

import { useEffect, useState } from "react";

const RETRY_DELAY_MS = 3000;

export interface BackendResource<T> {
  items: T[];
  /** True while the last attempt failed or returned nothing, and a retry is pending. */
  pending: boolean;
}

/**
 * Loads a one-shot list from the backend once the stream is live, and keeps trying until
 * it gets something.
 *
 * A plain `useEffect(..., [])` is wrong here: the first attempt can land before the backend
 * address is confirmed, or fail transiently, and the panel would then sit empty (and its
 * controls disabled) for the rest of the session with nothing explaining why.
 *
 * `load` must be a stable reference - define it at module scope or with `useCallback`.
 */
export function useBackendResource<T>(load: () => Promise<T[]>, ready: boolean): BackendResource<T> {
  const [items, setItems] = useState<T[]>([]);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!ready || items.length > 0) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const retry = () => {
      timer = setTimeout(() => setAttempt((a) => a + 1), RETRY_DELAY_MS);
    };

    load()
      .then((list) => {
        if (cancelled) return;
        if (list.length > 0) setItems(list);
        else retry();
      })
      .catch(() => {
        if (!cancelled) retry();
      });

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [ready, items.length, attempt, load]);

  return { items, pending: ready && items.length === 0 };
}
