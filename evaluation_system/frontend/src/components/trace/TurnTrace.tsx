import { Clock, Hash, WarningCircle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useEvaluationApi } from "../../api/context";
import type { StageName, TurnTrace as TurnTraceType } from "../../types/api";
import { Badge, statusTone } from "../ui/Badge";
import { Definition, ErrorState, SkeletonRows } from "../ui/States";
import { formatDuration, shortHash } from "../ui/format";
import { StageInspector } from "./StageInspector";
import { StageRail, type TraceView } from "./StageRail";

export function TurnTrace({ turnId, divergentStage, initialTrace }: { turnId: string; divergentStage?: StageName | null; initialTrace?: TurnTraceType }) {
  const api = useEvaluationApi();
  const [selected, setSelected] = useState<TraceView>(divergentStage || "NORMALIZATION");
  const query = useQuery({ queryKey: ["turn-trace", turnId], queryFn: () => api.turnTrace(turnId), initialData: initialTrace });
  if (query.isLoading) return <SkeletonRows count={5} />;
  if (query.isError) return <ErrorState title="اثر اجرای نوبت قابل دریافت نیست" error={query.error} retry={() => void query.refetch()} />;
  const trace = query.data!; const turn = trace.turn;
  const historyStage = trace.stages.find((stage) => stage.stage_name === "HISTORY");
  const derivedHistory = trace.stages.find((stage) => stage.stage_name === "CONTEXT_SELECTION")?.input_data?.history_messages ?? trace.stages.find((stage) => stage.stage_name === "REWRITE")?.input_data?.history_used;
  return <div className="turn-trace">
    <section className="trace-turn-facts"><div><span>پرسش کاربر</span><p dir="auto">{turn.raw_query}</p></div><div><span>پرسش نرمال‌شده</span><p dir="auto">{turn.normalized_query || "ناموجود"}</p></div><div><span>پرسش بازنویسی‌شده</span><p dir="auto">{turn.rewritten_query || "ناموجود"}</p></div><div><span>Intent / Score</span><p dir="ltr">{turn.actual_intent || "-"} / {turn.intent_score ?? "-"}</p></div><div className="trace-turn-answer"><span>پاسخ نهایی</span><p dir="auto">{turn.actual_answer || "هنوز پاسخی ثبت نشده است."}</p></div></section>
    <div className="trace-overview">
      <div><Badge tone={statusTone(turn.status, turn.infrastructure_error)}>{turn.infrastructure_error ? "Infrastructure Error" : turn.status}</Badge>{turn.fallback_used && <Badge tone="warning">Fallback</Badge>}</div>
      <dl><Definition label="هش تاریخچه قبل" ltr><code>{shortHash(turn.history_before_hash)}</code></Definition><Definition label="هش تاریخچه بعد" ltr><code>{shortHash(turn.history_after_hash)}</code></Definition><Definition label="زمان"><Clock size={15} /> {formatDuration(turn.total_latency_ms)}</Definition></dl>
    </div>
    {(turn.infrastructure_error || turn.error_code) && <div className="stage-error"><WarningCircle size={20} /><div><strong>Infrastructure Error</strong><p dir="ltr">{turn.error_code || "UNKNOWN_INFRASTRUCTURE_ERROR"}</p></div></div>}
    {turn.fallback_used && <div className="fallback-note"><Hash size={18} /><div><strong>Semantic Fallback</strong><p dir="ltr">{turn.fallback_reason || "UNSPECIFIED_FALLBACK"}</p></div></div>}
    <StageRail stages={trace.stages} selected={selected} onSelect={setSelected} divergentStage={divergentStage} fallbackUsed={turn.fallback_used} infrastructureError={turn.infrastructure_error} />
    {selected === "HISTORY" && !historyStage && derivedHistory != null ? <section className="history-panel"><header><strong>تاریخچه مشتق‌شده</strong><Badge tone="neutral">Derived, not a stage result</Badge></header><div className="artifact-columns"><Definition label="پرسش خام">{turn.raw_query}</Definition><Definition label="تاریخچه موجود در مراحل قدیمی">{typeof derivedHistory === "string" ? derivedHistory : JSON.stringify(derivedHistory, null, 2)}</Definition></div></section> : <StageInspector stage={trace.stages.find((stage) => stage.stage_name === selected)} stages={trace.stages} />}
  </div>;
}
