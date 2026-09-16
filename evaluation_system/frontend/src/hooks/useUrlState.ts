import { useCallback, useEffect, useState } from "react";
import type { StageName } from "../types/api";

export type PanelName = "overview" | "datasets" | "runs" | "stability" | "pipeline" | "system";

const availablePanels = new Set<PanelName>(["overview", "datasets", "runs", "stability", "pipeline"]);
const availableStages = new Set<StageName>([
  "NORMALIZATION", "HISTORY", "REWRITE", "INTENT", "RETRIEVAL", "RERANK", "CONTEXT_SELECTION", "PROMPT_BUILD", "GENERATION",
]);

export interface UrlState {
  panel: PanelName;
  runId: string | null;
  sessionId: string | null;
  turnId: string | null;
  stage: StageName | null;
}

export type UrlStateUpdater = (next: Partial<UrlState>, options?: { replace?: boolean }) => void;

function readState() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("panel");
  const normalized = requested === "dataset" ? "datasets" : requested;
  const runId = params.get("run");
  const panel = normalized && availablePanels.has(normalized as PanelName) ? normalized as PanelName : runId ? "runs" : "overview";
  const requestedStage = params.get("stage") as StageName | null;
  return {
    panel,
    runId,
    sessionId: params.get("session"),
    turnId: params.get("turn"),
    stage: requestedStage && availableStages.has(requestedStage) ? requestedStage : null,
  } satisfies UrlState;
}

export function useUrlState() {
  const [state, setState] = useState(readState);
  useEffect(() => {
    const onPop = () => setState(readState());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const update = useCallback<UrlStateUpdater>((next, options) => {
    const current = readState();
    const merged = { ...current, ...next };
    const params = new URLSearchParams();
    params.set("panel", merged.panel);
    if (merged.runId) params.set("run", merged.runId);
    if (merged.sessionId) params.set("session", merged.sessionId);
    if (merged.turnId) params.set("turn", merged.turnId);
    if (merged.stage) params.set("stage", merged.stage);
    window.history[options?.replace ? "replaceState" : "pushState"]({}, "", `${window.location.pathname}?${params}`);
    setState(merged);
  }, []);
  return { ...state, update };
}
