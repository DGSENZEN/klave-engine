"use client";

import { useEffect, useState } from "react";
import {
  getCosts,
  getProjectReviews,
  getRisks,
  getTablero,
  type CostReport,
  type ProjectReviews,
  type RiskReport,
  type Tablero,
} from "@/lib/api";
import { useProjectLive } from "@/components/ProjectLive";

/**
 * Cost report with live refresh: reloads on reconnect epochs (events may have
 * been skipped) and on committed costing/processing changes from any client.
 */
export function useCostReport(id: string): {
  costs: CostReport | null;
  error: boolean;
} {
  const [costs, setCosts] = useState<CostReport | null>(null);
  const [error, setError] = useState(false);
  const { latestEvent, connectionEpoch } = useProjectLive();

  useEffect(() => {
    let active = true;
    getCosts(id)
      .then((c) => {
        if (active) {
          setCosts(c);
          setError(false);
        }
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (latestEvent?.type !== "costing_updated" && latestEvent?.type !== "run_published")
      return;
    let active = true;
    getCosts(id)
      .then((c) => {
        if (active) setCosts(c);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [id, latestEvent]);

  return { costs, error };
}

/** Risk report is produced by processing, so only run_published invalidates it. */
export function useRiskReport(id: string): {
  risks: RiskReport | null;
  error: boolean;
} {
  const [risks, setRisks] = useState<RiskReport | null>(null);
  const [error, setError] = useState(false);
  const { latestEvent, connectionEpoch } = useProjectLive();

  useEffect(() => {
    let active = true;
    getRisks(id)
      .then((r) => {
        if (active) {
          setRisks(r);
          setError(false);
        }
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (latestEvent?.type !== "run_published") return;
    let active = true;
    getRisks(id)
      .then((r) => {
        if (active) setRisks(r);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [id, latestEvent]);

  return { risks, error };
}

const TABLERO_EVENTS = new Set([
  "job_updated",
  "run_published",
  "costing_updated",
  "review_updated",
  "gate_updated",
]);

/**
 * Board state with live refresh: almost every committed change moves some
 * node's facts, so any of the events above (or a reconnect) refetches.
 */
export function useTablero(id: string): {
  tablero: Tablero | null;
  error: boolean;
  refetch: () => void;
} {
  const [tablero, setTablero] = useState<Tablero | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const { latestEvent, connectionEpoch } = useProjectLive();

  useEffect(() => {
    let active = true;
    getTablero(id)
      .then((t) => {
        if (active) {
          setTablero(t);
          setError(false);
        }
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [id, connectionEpoch, attempt]);

  useEffect(() => {
    if (!latestEvent || !TABLERO_EVENTS.has(latestEvent.type)) return;
    let active = true;
    getTablero(id)
      .then((t) => {
        if (active) setTablero(t);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [id, latestEvent]);

  return { tablero, error, refetch: () => setAttempt((n) => n + 1) };
}

/** Reviews (exclusions, adjustments, verification) with live refresh. */
export function useProjectReviews(id: string): ProjectReviews | null {
  const [reviews, setReviews] = useState<ProjectReviews | null>(null);
  const { latestEvent, connectionEpoch } = useProjectLive();

  useEffect(() => {
    let active = true;
    getProjectReviews(id)
      .then((r) => active && setReviews(r))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (latestEvent?.type !== "review_updated" && latestEvent?.type !== "run_published") return;
    let active = true;
    getProjectReviews(id)
      .then((r) => active && setReviews(r))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [id, latestEvent]);

  return reviews;
}
