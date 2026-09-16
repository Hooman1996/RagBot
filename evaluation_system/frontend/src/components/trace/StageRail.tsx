import { Check, Minus, WarningCircle } from "@phosphor-icons/react";
import type { StageName, StageResult } from "../../types/api";

export type TraceView = StageName;

export const STAGES: { name: StageName; label: string }[] = [
  { name: "NORMALIZATION", label: "نرمال‌سازی" },
  { name: "HISTORY", label: "تاریخچه" },
  { name: "REWRITE", label: "بازنویسی" },
  { name: "INTENT", label: "نیت" },
  { name: "RETRIEVAL", label: "بازیابی" },
  { name: "RERANK", label: "بازرتبه‌بندی" },
  { name: "CONTEXT_SELECTION", label: "زمینه" },
  { name: "PROMPT_BUILD", label: "پرامپت" },
  { name: "GENERATION", label: "تولید" },
];

export function StageRail({ stages, selected, onSelect, divergentStage, fallbackUsed, infrastructureError }: { stages: StageResult[]; selected: TraceView; onSelect: (stage: TraceView) => void; divergentStage?: StageName | null; fallbackUsed?: boolean; infrastructureError?: boolean }) {
  const canonicalIndex = new Map(STAGES.map((item, index) => [item.name, index]));
  const ordered = [...STAGES].sort((a, b) => {
    const actualA = stages.find((stage) => stage.stage_name === a.name)?.stage_order;
    const actualB = stages.find((stage) => stage.stage_name === b.name)?.stage_order;
    if (actualA != null && actualB != null) return actualA - actualB;
    return canonicalIndex.get(a.name)! - canonicalIndex.get(b.name)!;
  });
  return <><div className="stage-legend" aria-label="راهنمای وضعیت مراحل"><span><i className="legend-dot legend-dot--normal" />Completed</span><span><i className="legend-dot legend-dot--diverged" />Diverged</span><span><i className="legend-dot legend-dot--fallback" />Fallback</span><span><i className="legend-dot legend-dot--error" />Error</span></div><div className="stage-rail" role="tablist" aria-label="مراحل خط لوله">
    {ordered.map((item) => {
    const stage = stages.find((candidate) => candidate.stage_name === item.name);
    const status = stage?.status || "PENDING";
    const first = divergentStage === item.name;
    const fallback = item.name === "GENERATION" && fallbackUsed;
    const error = status === "ERROR" || (item.name === "GENERATION" && infrastructureError);
    return <button key={item.name} role="tab" aria-selected={selected === item.name} className={`stage-segment stage-segment--${status.toLowerCase()} ${first ? "stage-segment--divergent" : ""} ${fallback ? "stage-segment--fallback" : ""} ${error ? "stage-segment--infra-error" : ""}`} onClick={() => onSelect(item.name)}>
      <span className="stage-segment__icon">{status === "ERROR" ? <WarningCircle size={15} /> : status === "SKIPPED" ? <Minus size={15} /> : status === "COMPLETED" ? <Check size={15} /> : null}</span>
      <span>{item.label}</span><small>{stage ? `${stage.duration_ms == null ? "-" : `${Math.round(stage.duration_ms)} ms`} | ${stage.input_hash ? "I" : "-"}${stage.output_hash ? "O" : "-"}` : "Unavailable"}</small>{first && <small>اولین واگرایی</small>}
    </button>;
  })}</div></>;
}
