import { Check, Clock, Database, Minus, WarningCircle } from "@phosphor-icons/react";
import type { StageName, StageResult } from "../../types/api";

export type TraceView = "HISTORY" | StageName | "ERRORS_TIMING";

export const STAGES: { name: StageName; label: string }[] = [
  { name: "NORMALIZATION", label: "نرمال‌سازی" },
  { name: "INTENT", label: "نیت" },
  { name: "REWRITE", label: "بازنویسی" },
  { name: "RETRIEVAL", label: "بازیابی" },
  { name: "RERANK", label: "بازرتبه‌بندی" },
  { name: "CONTEXT_SELECTION", label: "زمینه" },
  { name: "PROMPT_BUILD", label: "پرامپت" },
  { name: "GENERATION", label: "تولید" },
];

export function StageRail({ stages, selected, onSelect, divergentStage, fallbackUsed, infrastructureError }: { stages: StageResult[]; selected: TraceView; onSelect: (stage: TraceView) => void; divergentStage?: StageName | null; fallbackUsed?: boolean; infrastructureError?: boolean }) {
  return <><div className="stage-legend" aria-label="راهنمای وضعیت مراحل"><span><i className="legend-dot legend-dot--normal" />Normal</span><span><i className="legend-dot legend-dot--diverged" />Diverged</span><span><i className="legend-dot legend-dot--fallback" />Fallback</span><span><i className="legend-dot legend-dot--error" />Infra error</span></div><div className="stage-rail" role="tablist" aria-label="مراحل خط لوله">
    <button role="tab" aria-selected={selected === "HISTORY"} className="stage-segment stage-segment--input" onClick={() => onSelect("HISTORY")}><span className="stage-segment__icon"><Database size={15} /></span><span>ورودی و تاریخچه</span><small>Input</small></button>
    {STAGES.map((item) => {
    const stage = stages.find((candidate) => candidate.stage_name === item.name);
    const status = stage?.status || "PENDING";
    const first = divergentStage === item.name;
    const fallback = item.name === "GENERATION" && fallbackUsed;
    const error = status === "ERROR" || (item.name === "GENERATION" && infrastructureError);
    return <button key={item.name} role="tab" aria-selected={selected === item.name} className={`stage-segment stage-segment--${status.toLowerCase()} ${first ? "stage-segment--divergent" : ""} ${fallback ? "stage-segment--fallback" : ""} ${error ? "stage-segment--infra-error" : ""}`} onClick={() => onSelect(item.name)}>
      <span className="stage-segment__icon">{status === "ERROR" ? <WarningCircle size={15} /> : status === "SKIPPED" ? <Minus size={15} /> : status === "COMPLETED" ? <Check size={15} /> : null}</span>
      <span>{item.label}</span>{first && <small>اولین واگرایی</small>}
    </button>;
  })}<button role="tab" aria-selected={selected === "ERRORS_TIMING"} className={`stage-segment ${infrastructureError ? "stage-segment--infra-error" : ""}`} onClick={() => onSelect("ERRORS_TIMING")}><span className="stage-segment__icon"><Clock size={15} /></span><span>خطا و زمان‌بندی</span><small>Timing</small></button></div></>;
}
