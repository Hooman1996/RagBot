import { RunInspector } from "./RunInspector";
import { RunsIndex } from "./RunsIndex";

export function Runs({ runId, onRunOpen, onBack }: { runId: string | null; onRunOpen: (id: string) => void; onBack: () => void }) {
  return runId ? <RunInspector runId={runId} onBack={onBack} /> : <RunsIndex onOpen={onRunOpen} />;
}
