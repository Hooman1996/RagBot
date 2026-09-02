import { useCallback, useEffect, useState } from "react";

export type PanelName = "dataset" | "stability";

function readState() {
  const params = new URLSearchParams(window.location.search);
  const panel = params.get("panel") === "stability" ? "stability" : "dataset";
  return { panel: panel as PanelName, runId: params.get("run") };
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
