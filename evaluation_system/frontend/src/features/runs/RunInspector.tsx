import { ArrowRight, Broadcast, Clock, Pause, WarningCircle } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useEvaluationApi } from "../../api/context";
import { TurnTrace } from "../../components/trace/TurnTrace";
import { Button } from "../../components/ui/Button";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { EmptyState, ErrorState, SkeletonRows } from "../../components/ui/States";
import { formatDate, formatDuration, shortHash } from "../../components/ui/format";
import { useRunEvents } from "../../hooks/useRunEvents";
import type { RunSession, RunTurn } from "../../types/api";

const ACTIVE = new Set(["PENDING", "RUNNING"]);

export function RunInspector({ runId, onBack }: { runId: string; onBack: () => void }) {
  const api = useEvaluationApi(); const client = useQueryClient();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId), refetchInterval: (query) => ACTIVE.has(query.state.data?.status || "") ? 5_000 : false });
  const sessions = useQuery({ queryKey: ["run-sessions", runId], queryFn: () => api.runSessions(runId), refetchInterval: (query) => ACTIVE.has(run.data?.status || "") ? 5_000 : false });
  const dataset = useQuery({ queryKey: ["dataset", run.data?.dataset_id], queryFn: () => api.dataset(run.data!.dataset_id!), enabled: !!run.data?.dataset_id });
  const active = ACTIVE.has(run.data?.status || "");
  const live = useRunEvents(runId, active);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const detail = useQuery({ queryKey: ["run-session", sessionId], queryFn: () => api.runSession(sessionId!), enabled: !!sessionId, refetchInterval: active ? 5_000 : false });
  const [turnId, setTurnId] = useState<string | null>(null);
  useEffect(() => {
    const items = sessions.data || [];
    if (!items.length) { setSessionId(null); return; }
    if (!sessionId || !items.some((item) => item.id === sessionId)) setSessionId(items[0].id);
  }, [sessionId, sessions.data]);
  useEffect(() => {
    const turns = detail.data?.turns || [];
    if (!turns.length) { setTurnId(null); return; }
    if (!turnId || !turns.some((item) => item.id === turnId)) setTurnId(turns[0].id);
  }, [detail.data, turnId]);
  const selectedSession = sessions.data?.find((item) => item.id === sessionId);
  const selectedTurn = detail.data?.turns.find((item) => item.id === turnId);
  const cancel = useMutation({ mutationFn: () => api.cancelRun(runId), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["run", runId] }); } });

  if (run.isLoading) return <div className="run-inspector"><SkeletonRows count={8} /></div>;
  if (run.isError) return <div className="run-inspector"><button className="back-link" onClick={onBack}><ArrowRight />بازگشت به اجراها</button><ErrorState title="اجرا پیدا نشد یا قابل دریافت نیست" error={run.error} retry={() => void run.refetch()} /></div>;
  const value = run.data!;
  const elapsed = value.started_at ? Math.max(0, Date.parse(value.finished_at || new Date().toISOString()) - Date.parse(value.started_at)) : null;
  return <main className="run-inspector">
    <button className="back-link" onClick={onBack}><ArrowRight />بازگشت به اجراها</button>
    <header className="run-header surface">
      <div className="run-header__identity"><div><span className="run-type">{value.run_type}</span><h1 dir="ltr" title={value.id}>{value.id}</h1><p>{dataset.data?.filename || (value.dataset_id ? shortHash(value.dataset_id) : "بدون مجموعه داده")}</p></div><div className="run-header__actions"><StatusBadge status={value.status} />{active && <Button variant="secondary" onClick={() => cancel.mutate()} disabled={cancel.isPending}><Pause />لغو اجرا</Button>}</div></div>
      <dl className="run-header__metrics">
        <div><dt>جلسه‌ها</dt><dd dir="ltr">{value.completed_sessions} / {value.total_sessions}</dd></div><div><dt>نوبت‌ها</dt><dd dir="ltr">{value.completed_turns} / {value.total_turns}</dd></div><div><dt>Fallback</dt><dd>{value.fallback_count}</dd></div><div><dt>خطا</dt><dd>{value.error_count}</dd></div><div><dt>زیرساخت</dt><dd>{value.infrastructure_error_count}</dd></div><div><dt>مدت</dt><dd>{formatDuration(elapsed)}</dd></div><div><dt>Git SHA</dt><dd><code dir="ltr" title={value.git_commit_sha || ""}>{shortHash(value.git_commit_sha)}</code></dd></div>
      </dl>
      <div className="run-header__timeline"><span>ایجاد: {formatDate(value.created_at)}</span><span>شروع: {formatDate(value.started_at)}</span><span>پایان: {formatDate(value.finished_at)}</span>{active && <span className={`live-state is-${live.connection}`}><Broadcast />{live.connection === "live" ? "اتصال زنده" : live.connection === "connecting" ? "در حال اتصال" : live.connection === "reconnecting" ? "اتصال مجدد" : "بسته"}</span>}</div>
      {active && live.errorCode && <div className="live-warning"><WarningCircle />اتصال زنده موقتاً در دسترس نیست. داده‌های PostgreSQL همچنان دوره‌ای به‌روزرسانی می‌شوند.</div>}
      {value.failure_code && <div className="run-failure"><WarningCircle /><code dir="ltr">{value.failure_code}</code></div>}
    </header>
    {sessions.isLoading ? <section className="surface runs-loading"><SkeletonRows count={6} /></section> : sessions.isError ? <ErrorState title="جلسه‌های اجرا قابل دریافت نیستند" error={sessions.error} retry={() => void sessions.refetch()} /> : !(sessions.data || []).length ? <EmptyState title="هنوز جلسه‌ای ثبت نشده است" message={active ? "جلسه‌ها پس از شروع پردازش در اینجا ظاهر می‌شوند." : "این اجرا جلسه‌ای برای بازرسی ندارد."} /> : <div className="run-workspace">
      <RunSessionNavigator sessions={sessions.data!} selectedId={sessionId} onSelect={setSessionId} />
      <section className="run-turn-pane surface">
        <div className="workspace-pane-title"><h2>نوبت‌ها</h2><span>{selectedSession?.turn_count || 0}</span></div>
        {detail.isLoading ? <SkeletonRows count={5} /> : detail.isError ? <ErrorState title="جزئیات جلسه قابل دریافت نیست" error={detail.error} retry={() => void detail.refetch()} /> : !detail.data?.turns.length ? <EmptyState title="هنوز نوبتی ثبت نشده است" message="با ثبت نخستین نوبت، جزئیات آن در این بخش ظاهر می‌شود." /> : <div className="run-turn-list">{detail.data.turns.map((turn) => <TurnButton key={turn.id} turn={turn} selected={turn.id === turnId} onClick={() => setTurnId(turn.id)} />)}</div>}
      </section>
      <section className="run-trace-pane">
        {selectedTurn && <div className="selected-turn-summary surface"><div><span>پرسش کاربر</span><h2 dir="auto">{selectedTurn.raw_query}</h2></div><div className="selected-answer"><span>پاسخ نهایی</span><p dir="auto">{selectedTurn.actual_answer || "هنوز پاسخی ثبت نشده است."}</p></div><dl><div><dt>Intent</dt><dd>{selectedTurn.actual_intent || "-"}</dd></div><div><dt>زمان کل</dt><dd>{formatDuration(selectedTurn.total_latency_ms)}</dd></div><div><dt>Fallback</dt><dd>{selectedTurn.fallback_used ? selectedTurn.fallback_reason || "فعال" : "خیر"}</dd></div>{selectedTurn.error_code && <div><dt>کد خطا</dt><dd><code dir="ltr">{selectedTurn.error_code}</code></dd></div>}</dl></div>}
        {turnId ? <TurnTrace turnId={turnId} divergentStage={selectedSession && selectedSession.first_divergent_turn === selectedTurn?.turn_index ? selectedSession.first_divergent_stage : null} /> : <EmptyState title="یک نوبت را انتخاب کنید" message="برای مشاهده مراحل خط لوله، یک نوبت از ستون میانی انتخاب کنید." />}
      </section>
    </div>}
  </main>;
}

function RunSessionNavigator({ sessions, selectedId, onSelect }: { sessions: RunSession[]; selectedId: string | null; onSelect: (id: string) => void }) {
  return <aside className="run-session-pane surface"><div className="workspace-pane-title"><h2>جلسه‌ها / تکرارها</h2><span>{sessions.length}</span></div><div className="run-session-list">{sessions.map((session) => <button key={session.id} className={session.id === selectedId ? "is-selected" : ""} onClick={() => onSelect(session.id)}><span className="session-name" dir="auto">{session.source_session_id || session.synthetic_label || "جلسه مصنوعی"}</span><StatusBadge status={session.status} /><small>تکرار {session.repeat_index}</small><small>{session.turn_count} نوبت</small><small><Clock />{formatDuration(session.total_latency_ms)}</small><span className="session-counts">F {session.fallback_count} / E {session.error_count} / I {session.infrastructure_error_count}</span>{session.first_divergent_turn != null && <span className="divergence-note">واگرایی: نوبت {session.first_divergent_turn}، {session.first_divergent_stage}</span>}</button>)}</div></aside>;
}

function TurnButton({ turn, selected, onClick }: { turn: RunTurn; selected: boolean; onClick: () => void }) {
  return <button className={selected ? "is-selected" : ""} onClick={onClick}><span className="turn-index">{turn.turn_index}</span><strong dir="auto">{turn.raw_query}</strong><small>{turn.actual_intent || "Intent unavailable"}</small><small>{formatDuration(turn.total_latency_ms)}</small><StatusBadge status={turn.infrastructure_error || turn.status === "ERROR" ? "FAILED" : turn.status} />{turn.fallback_used && <span className="turn-flag is-fallback">Fallback</span>}{turn.infrastructure_error && <span className="turn-flag is-error">Infra</span>}</button>;
}
