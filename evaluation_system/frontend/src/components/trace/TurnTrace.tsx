import { Clock, Hash, WarningCircle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../../app/auth";
import type { StageName, TurnTrace as TurnTraceType } from "../../types/api";
import { Badge, statusTone } from "../ui/Badge";
import { Definition, ErrorState, SkeletonRows } from "../ui/States";
import { formatDuration, shortHash } from "../ui/format";
import { StageInspector } from "./StageInspector";
import { StageRail, type TraceView } from "./StageRail";

export function TurnTrace({ turnId, divergentStage, initialTrace }: { turnId: string; divergentStage?: StageName | null; initialTrace?: TurnTraceType }) {
  const { api } = useAuth();
  const [selected, setSelected] = useState<TraceView>(divergentStage || "HISTORY");
  const query = useQuery({ queryKey: ["turn-trace", turnId], queryFn: () => api.turnTrace(turnId), initialData: initialTrace });
  if (query.isLoading) return <SkeletonRows count={5} />;
  if (query.isError) return <ErrorState title="اثر اجرای نوبت قابل دریافت نیست" error={query.error} retry={() => void query.refetch()} />;
  const trace = query.data!; const turn = trace.turn;
  const history = trace.stages.find((stage) => stage.stage_name === "CONTEXT_SELECTION")?.input_data?.history_messages ?? trace.stages.find((stage) => stage.stage_name === "REWRITE")?.input_data?.history_used ?? "[بدون مکالمه قبلی]";
  return <div className="turn-trace">
    <div className="trace-overview">
      <div><Badge tone={statusTone(turn.status, turn.infrastructure_error)}>{turn.infrastructure_error ? "Infrastructure Error" : turn.status}</Badge>{turn.fallback_used && <Badge tone="warning">Fallback</Badge>}</div>
      <dl><Definition label="هش تاریخچه قبل" ltr><code>{shortHash(turn.history_before_hash)}</code></Definition><Definition label="هش تاریخچه بعد" ltr><code>{shortHash(turn.history_after_hash)}</code></Definition><Definition label="زمان"><Clock size={15} /> {formatDuration(turn.total_latency_ms)}</Definition></dl>
    </div>
    {(turn.infrastructure_error || turn.error_code) && <div className="stage-error"><WarningCircle size={20} /><div><strong>Infrastructure Error</strong><p dir="ltr">{turn.error_code || "UNKNOWN_INFRASTRUCTURE_ERROR"}</p></div></div>}
    {turn.fallback_used && <div className="fallback-note"><Hash size={18} /><div><strong>Semantic Fallback</strong><p dir="ltr">{turn.fallback_reason || "UNSPECIFIED_FALLBACK"}</p></div></div>}
    <StageRail stages={trace.stages} selected={selected} onSelect={setSelected} divergentStage={divergentStage} fallbackUsed={turn.fallback_used} infrastructureError={turn.infrastructure_error} />
    {selected === "HISTORY" ? <section className="history-panel"><h4>Input / History</h4><div className="artifact-columns"><Definition label="پرسش خام">{turn.raw_query}</Definition><Definition label="تاریخچه دقیق استفاده‌شده">{typeof history === "string" ? history : JSON.stringify(history, null, 2)}</Definition></div></section> : selected === "ERRORS_TIMING" ? <section className="stage-inspector timing-inspector"><header><span>Timing / Errors</span><code dir="ltr">{turn.error_code || "NO_TURN_ERROR"}</code></header><div className="timing-grid">{trace.stages.map((stage) => <div key={stage.stage_name}><span>{stage.stage_name}</span><strong>{formatDuration(stage.duration_ms)}</strong><Badge tone={statusTone(stage.status)}>{stage.status}</Badge>{stage.error_code && <code dir="ltr">{stage.error_code}</code>}</div>)}</div></section> : <StageInspector stage={trace.stages.find((stage) => stage.stage_name === selected)} stages={trace.stages} />}
  </div>;
}
