import type { StageName } from "../../types/api";
import { StabilityResults } from "./StabilityResults";
import { StabilityRunSetup } from "./StabilityRunSetup";

export function StabilityInspector({ activeRunId, onRunOpen, onRunInspect, onPipelineOpen }: {
  activeRunId: string | null;
  onRunOpen: (id: string) => void;
  onRunInspect?: (id: string) => void;
  onPipelineOpen?: (sessionId: string, turnId: string, stage: StageName) => void;
}) {
  return activeRunId
    ? <StabilityResults runId={activeRunId} onRunInspect={onRunInspect} onPipelineOpen={onPipelineOpen} />
    : <StabilityRunSetup onRunOpen={onRunOpen} />;
}
