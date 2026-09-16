import { useCallback, useEffect, useState } from "react";

export type PanelName = "overview" | "datasets" | "runs" | "stability" | "pipeline" | "system";

const availablePanels = new Set<PanelName>(["overview", "datasets", "runs", "stability"]);

function readState() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("panel");
  const normalized = requested === "dataset" ? "datasets" : requested;
  const runId = params.get("run");
  const panel = normalized && availablePanels.has(normalized as PanelName) ? normalized as PanelName : runId ? "runs" : "overview";
  return { panel, runId };
}

export function useUrlState() {
  const [state, setState] = useState(readState);
  useEffect(() => {
    const onPop = () => setState(readState());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const update = useCallback((next: Partial<{ panel: PanelName; runId: string | null }>) => {
    const current = readState();
    const merged = { ...current, ...next };
    const params = new URLSearchParams();
    params.set("panel", merged.panel);
    if (merged.runId) params.set("run", merged.runId);
    window.history.pushState({}, "", `${window.location.pathname}?${params}`);
    setState(merged);
  }, []);
  return { ...state, update };
}
