import { Clock, Hash, WarningCircle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useEvaluationApi } from "../../api/context";
import type { StageName, StageResult, TurnTrace as TurnTraceType } from "../../types/api";
import { Badge, statusTone } from "../ui/Badge";
import { Definition, ErrorState, SkeletonRows } from "../ui/States";
import { formatDuration, shortHash } from "../ui/format";
import { StageInspector } from "./StageInspector";
import { StageRail, type TraceView } from "./StageRail";

export function TurnTrace({ turnId, divergentStage, initialTrace, selectedStage, onStageSelect }: { turnId: string; divergentStage?: StageName | null; initialTrace?: TurnTraceType; selectedStage?: StageName; onStageSelect?: (stage: StageName) => void }) {
  const api = useEvaluationApi();
  const [localSelected, setLocalSelected] = useState<TraceView>(divergentStage || "NORMALIZATION");
  const selected = selectedStage || localSelected;
  const setSelected = (next: TraceView) => { setLocalSelected(next); onStageSelect?.(next); };
  const query = useQuery({ queryKey: ["turn-trace", turnId], queryFn: () => api.turnTrace(turnId), initialData: initialTrace });
  if (query.isLoading) return <SkeletonRows count={5} />;
  if (query.isError) return <ErrorState title="اثر اجرای نوبت قابل دریافت نیست" error={query.error} retry={() => void query.refetch()} />;
  const trace = query.data!; const turn = trace.turn;
  return <div className="turn-trace">
    <section className="trace-turn-facts"><div><span>پرسش کاربر</span><p dir="auto">{turn.raw_query}</p></div><div><span>پرسش نرمال‌شده</span><p dir="auto">{turn.normalized_query || "ناموجود"}</p></div><div><span>پرسش بازنویسی‌شده</span><p dir="auto">{turn.rewritten_query || "ناموجود"}</p></div><div><span>Intent / Score</span><p dir="ltr">{turn.actual_intent || "-"} / {turn.intent_score ?? "-"}</p></div><div className="trace-turn-answer"><span>پاسخ نهایی</span><p dir="auto">{turn.actual_answer || "هنوز پاسخی ثبت نشده است."}</p></div></section>
    <div className="trace-overview">
      <div><Badge tone={statusTone(turn.status, turn.infrastructure_error)}>{turn.infrastructure_error ? "Infrastructure Error" : turn.status}</Badge>{turn.fallback_used && <Badge tone="warning">Fallback</Badge>}</div>
      <dl><Definition label="هش تاریخچه قبل" ltr><code>{shortHash(turn.history_before_hash)}</code></Definition><Definition label="هش تاریخچه بعد" ltr><code>{shortHash(turn.history_after_hash)}</code></Definition><Definition label="زمان"><Clock size={15} /> {formatDuration(turn.total_latency_ms)}</Definition></dl>
    </div>
    {(turn.infrastructure_error || turn.error_code) && <div className="stage-error"><WarningCircle size={20} /><div><strong>Infrastructure Error</strong><p dir="ltr">{turn.error_code || "UNKNOWN_INFRASTRUCTURE_ERROR"}</p></div></div>}
    {turn.fallback_used && <div className="fallback-note"><Hash size={18} /><div><strong>Semantic Fallback</strong><p dir="ltr">{turn.fallback_reason || "UNSPECIFIED_FALLBACK"}</p></div></div>}
    <StageRail stages={trace.stages} selected={selected} onSelect={setSelected} divergentStage={divergentStage} fallbackUsed={turn.fallback_used} infrastructureError={turn.infrastructure_error} />
    {["RETRIEVAL", "RERANK", "CONTEXT_SELECTION"].includes(selected) && <div className="artifact-flow" aria-label="جریان بازیابی تا انتخاب زمینه"><button type="button" aria-current={selected === "RETRIEVAL" ? "step" : undefined} onClick={() => setSelected("RETRIEVAL")}>Retrieval</button><span>←</span><button type="button" aria-current={selected === "RERANK" ? "step" : undefined} onClick={() => setSelected("RERANK")}>Rerank</button><span>←</span><button type="button" aria-current={selected === "CONTEXT_SELECTION" ? "step" : undefined} onClick={() => setSelected("CONTEXT_SELECTION")}>Selected Context</button></div>}
    <StageInspector stage={trace.stages.find((stage) => stage.stage_name === selected)} stages={trace.stages} />
    <StageSummary stages={trace.stages} selected={selected} onSelect={setSelected} />
  </div>;
}

function StageSummary({ stages, selected, onSelect }: { stages: StageResult[]; selected: StageName; onSelect: (stage: StageName) => void }) {
  const ordered = [...stages].sort((a, b) => a.stage_order - b.stage_order);
  const maxDuration = Math.max(0, ...ordered.map((item) => item.duration_ms || 0));
  if (!ordered.length) return <div className="empty-inline">داده‌ای برای مراحل این trace ثبت نشده است.</div>;
  return <section className="trace-technical-summary">
    <div className="workspace-pane-title"><h2>خلاصه فنی مراحل</h2><span>{ordered.length}</span></div>
    <div className="trace-summary-grid"><div className="table-wrap"><table className="data-table compact stage-summary-table"><thead><tr><th>Stage</th><th>Order</th><th>Status</th><th>Duration</th><th>Input Hash</th><th>Output Hash</th><th>Error Code</th></tr></thead><tbody>{ordered.map((item) => <tr key={item.stage_name} className={selected === item.stage_name ? "is-selected" : ""} onClick={() => onSelect(item.stage_name)}><td><button type="button" onClick={() => onSelect(item.stage_name)}>{item.stage_name}</button></td><td>{item.stage_order}</td><td>{item.status}</td><td>{formatDuration(item.duration_ms)}</td><td><code dir="ltr" title={item.input_hash || ""}>{shortHash(item.input_hash)}</code></td><td><code dir="ltr" title={item.output_hash || ""}>{shortHash(item.output_hash)}</code></td><td><code dir="ltr">{item.error_code || "-"}</code></td></tr>)}</tbody></table></div>
      <div className="stage-latency" aria-label="مقایسه زمان مراحل"><h3>زمان مراحل</h3>{ordered.map((item) => <button type="button" key={item.stage_name} onClick={() => onSelect(item.stage_name)}><span dir="ltr">{item.stage_name}</span><strong dir="ltr">{item.duration_ms == null ? "-" : `${Math.round(item.duration_ms)} ms`}</strong><i style={{ width: item.duration_ms != null && maxDuration > 0 ? `${Math.max(2, item.duration_ms / maxDuration * 100)}%` : "0" }} /></button>)}</div>
    </div>
  </section>;
}
