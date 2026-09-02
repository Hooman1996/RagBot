import { CaretDown, CaretLeft, ChatCircleText } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../../app/auth";
import type { RunSession, RunTurn } from "../../types/api";
import { Badge, statusTone } from "../ui/Badge";
import { ErrorState, SkeletonRows } from "../ui/States";
import { formatDate, formatDuration } from "../ui/format";
import { TurnTrace } from "../trace/TurnTrace";

export function SessionResult({ session }: { session: RunSession }) {
  const { api } = useAuth(); const [openTurn, setOpenTurn] = useState<string | null>(null);
  const detail = useQuery({ queryKey: ["run-session", session.id], queryFn: () => api.runSession(session.id) });
  const lineage = useQuery({ queryKey: ["dataset-turns", session.dataset_session_id], queryFn: () => api.datasetTurns(session.dataset_session_id!), enabled: !!session.dataset_session_id });
  if (detail.isLoading) return <SkeletonRows count={3} />;
  if (detail.isError) return <ErrorState title="جزئیات جلسه قابل دریافت نیست" error={detail.error} retry={() => void detail.refetch()} />;
  return <div className="session-detail">
    <dl className="session-summary"><div><dt>شناسه منبع</dt><dd dir="auto">{session.source_session_id || session.synthetic_label || "جلسه مصنوعی"}</dd></div><div><dt>تکرار</dt><dd>{session.repeat_index}</dd></div><div><dt>شروع</dt><dd>{formatDate(session.started_at)}</dd></div><div><dt>مدت</dt><dd>{formatDuration(session.total_latency_ms)}</dd></div></dl>
    <div className="turn-list">{detail.data!.turns.map((turn: RunTurn) => {
      const source = lineage.data?.find((item) => item.turn_index === turn.turn_index);
      const open = openTurn === turn.id;
      return <article className={`turn-result ${open ? "is-open" : ""}`} key={turn.id}>
        <button className="turn-result__head" onClick={() => setOpenTurn(open ? null : turn.id)} aria-expanded={open}>
          <span className="turn-number"><ChatCircleText size={17} />نوبت {turn.turn_index}</span>
          <span className="turn-query" dir="auto">{turn.raw_query}</span>
          <span>{source?.source_timestamp ? formatDate(source.source_timestamp) : source?.source_time_raw || "بدون زمان"}</span>
          {turn.fallback_used && <Badge tone="warning">Fallback</Badge>}
          {turn.infrastructure_error && <Badge tone="danger">Infrastructure Error</Badge>}
          <Badge tone={statusTone(turn.status, turn.infrastructure_error)}>{turn.status}</Badge>
          <span>{formatDuration(turn.total_latency_ms)}</span>{open ? <CaretDown /> : <CaretLeft />}
        </button>
        <div className="turn-answer" dir="auto"><strong>پاسخ RagBot</strong><p>{turn.actual_answer || "پاسخی ثبت نشده است."}</p></div>
        {open && <TurnTrace turnId={turn.id} divergentStage={session.first_divergent_turn === turn.turn_index ? session.first_divergent_stage : null} />}
      </article>;
    })}</div>
  </div>;
}
