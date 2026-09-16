import { DatabaseGate } from "../components/database-setup/DatabaseGate";
import { useUrlState } from "../hooks/useUrlState";
import { DatasetInspector } from "../features/dataset-inspector/DatasetInspector";
import { StabilityInspector } from "../features/stability-inspector/StabilityInspector";
import { Overview } from "../features/overview/Overview";
import { AppShell } from "../components/shell/AppShell";
import { Runs } from "../features/runs/Runs";
import { PipelineExplorer } from "../features/pipeline/PipelineExplorer";
import { System } from "../features/system/System";
import type { Run } from "../types/api";

export function App() {
  const { panel, runId, sessionId, turnId, stage, update } = useUrlState();
  const navigate = (next: typeof panel) => update({ panel: next, runId: null, sessionId: null, turnId: null, stage: null });
  const openRun = (run: Run) => update({ panel: "runs", runId: run.id });
  return (
    <DatabaseGate>
      <AppShell panel={panel} onNavigate={navigate}>
        {panel === "overview" && <Overview onRunOpen={openRun} />}
        {panel === "datasets" && <DatasetInspector activeRunId={null} onRunOpen={(id) => update({ panel: "runs", runId: id })} />}
        {panel === "runs" && <Runs runId={runId} onRunOpen={(id) => update({ panel: "runs", runId: id })} onBack={() => update({ panel: "runs", runId: null })} />}
        {panel === "stability" && <StabilityInspector activeRunId={runId} onRunOpen={(id) => update({ runId: id })} onRunInspect={(id) => update({ panel: "runs", runId: id })} onPipelineOpen={(sessionId, turnId, stage) => update({ panel: "pipeline", runId, sessionId, turnId, stage })} />}
        {panel === "pipeline" && <PipelineExplorer runId={runId} sessionId={sessionId} turnId={turnId} stage={stage} onUrlChange={update} />}
        {panel === "system" && <System />}
      </AppShell>
    </DatabaseGate>
  );
}
