"use client";

import { useEffect, useState } from "react";
import { getCosts, getRisks, type CostReport, type RiskReport } from "@/lib/api";
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
