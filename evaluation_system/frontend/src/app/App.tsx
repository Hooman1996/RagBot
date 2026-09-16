import { DatabaseGate } from "../components/database-setup/DatabaseGate";
import { useUrlState } from "../hooks/useUrlState";
import { DatasetInspector } from "../features/dataset-inspector/DatasetInspector";
import { StabilityInspector } from "../features/stability-inspector/StabilityInspector";
import { Overview } from "../features/overview/Overview";
import { AppShell } from "../components/shell/AppShell";
import type { Run } from "../types/api";

export function App() {
  const { panel, runId, update } = useUrlState();
  const navigate = (next: typeof panel) => update({ panel: next, runId: null });
  const openRun = (run: Run) => update({ panel: run.run_type === "DATASET_INSPECTION" ? "datasets" : "stability", runId: run.id });
  return (
    <DatabaseGate>
      <AppShell panel={panel} onNavigate={navigate}>
        {panel === "overview" && <Overview onRunOpen={openRun} />}
        {panel === "datasets" && <DatasetInspector activeRunId={runId} onRunOpen={(id) => update({ runId: id })} />}
        {panel === "stability" && <StabilityInspector activeRunId={runId} onRunOpen={(id) => update({ runId: id })} />}
      </AppShell>
    </DatabaseGate>
  );
}
