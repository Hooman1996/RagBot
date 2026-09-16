import { ArrowSquareOut, GitBranch, WarningCircle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useEvaluationApi } from "../../api/context";
import { PageHeader } from "../../components/shell/PageHeader";
import { TurnTrace } from "../../components/trace/TurnTrace";
import { Button } from "../../components/ui/Button";
import { EmptyState, ErrorState, SkeletonRows } from "../../components/ui/States";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { formatDate, shortHash } from "../../components/ui/format";
import type { UrlStateUpdater } from "../../hooks/useUrlState";
import type { Run, StageName } from "../../types/api";
import { PipelineRunPicker } from "./PipelineRunPicker";
import { PipelineSessionPicker } from "./PipelineSessionPicker";
import { PipelineTurnPicker } from "./PipelineTurnPicker";

const ACTIVE = new Set(["PENDING", "RUNNING"]);

export function PipelineExplorer({ runId, sessionId, turnId, stage, onUrlChange }: { runId: string | null; sessionId: string | null; turnId: string | null; stage: StageName | null; onUrlChange: UrlStateUpdater }) {
  const api = useEvaluationApi();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 10_000 });
  const runExists = !!runId && !!runs.data?.some((item) => item.id === runId);
  const selectedRun = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId!), enabled: runExists, refetchInterval: (query) => ACTIVE.has(query.state.data?.status || "") ? 5_000 : false });
  const sessions = useQuery({ queryKey: ["run-sessions", runId], queryFn: () => api.runSessions(runId!), enabled: runExists, refetchInterval: ACTIVE.has(selectedRun.data?.status || "") ? 5_000 : false });
  const sessionExists = !!sessionId && !!sessions.data?.some((item) => item.id === sessionId);
  const detail = useQuery({ queryKey: ["run-session", sessionId], queryFn: () => api.runSession(sessionId!), enabled: sessionExists, refetchInterval: ACTIVE.has(selectedRun.data?.status || "") ? 5_000 : false });
  const selectedSession = sessions.data?.find((item) => item.id === sessionId);
  const selectedTurn = detail.data?.turns.find((item) => item.id === turnId);

  useEffect(() => {
    if (!runId || !sessions.data?.length) return;
    if (!sessionId || !sessions.data.some((item) => item.id === sessionId)) onUrlChange({ sessionId: sessions.data[0].id, turnId: null, stage: null }, { replace: true });
  }, [onUrlChange, runId, sessionId, sessions.data]);
  useEffect(() => {
    if (!sessionId || !detail.data?.turns.length) return;
    if (!turnId || !detail.data.turns.some((item) => item.id === turnId)) onUrlChange({ turnId: detail.data.turns[0].id, stage: "NORMALIZATION" }, { replace: true });
  }, [detail.data, onUrlChange, sessionId, turnId]);
  useEffect(() => {
    if (turnId && !stage) onUrlChange({ stage: "NORMALIZATION" }, { replace: true });
  }, [onUrlChange, stage, turnId]);

  const selectRun = (id: string) => onUrlChange({ runId: id, sessionId: null, turnId: null, stage: null });
  const selectSession = (id: string) => onUrlChange({ sessionId: id, turnId: null, stage: null });
  const selectTurn = (id: string) => onUrlChange({ turnId: id, stage: "NORMALIZATION" });
  const selectStage = (next: StageName) => onUrlChange({ stage: next });

  return <main className="pipeline-page">
    <PageHeader title="خط لوله" description="ردیابی دقیق ورودی، خروجی و آثار هر مرحله برای هر نوبت ارزیابی‌شده." />
    <p className="pipeline-scope-note"><GitBranch size={15} />ابتدا اجرا را انتخاب کنید. فیلترهای جلسه و نوبت فقط روی داده‌های بارگذاری‌شده اعمال می‌شوند.</p>
    {runs.isLoading ? <section className="surface pipeline-loading"><SkeletonRows count={8} /></section> : runs.isError ? <ErrorState title="فهرست اجراها قابل دریافت نیست" error={runs.error} retry={() => void runs.refetch()} /> : !runs.data?.length ? <EmptyState title="اجرایی برای بازرسی وجود ندارد" message="پس از ثبت یک اجرای ارزیابی، رد آن در این بخش قابل بررسی است." /> : <div className="pipeline-workspace">
      <aside className="pipeline-locator surface" aria-label="Trace Locator">
        <header><div><span>Trace Locator</span><strong>انتخاب رد اجرا</strong></div>{runId && <button type="button" className="pipeline-clear" onClick={() => onUrlChange({ runId: null, sessionId: null, turnId: null, stage: null })}>پاک کردن</button>}</header>
        <PipelineRunPicker runs={runs.data} selectedId={runId} onSelect={selectRun} />
        {runId && !runExists && <div className="pipeline-inline-error"><WarningCircle /><span>این Run ID در فهرست اجراها وجود ندارد.</span></div>}
        {runExists && (sessions.isLoading ? <div className="pipeline-picker-loading"><SkeletonRows count={3} /></div> : sessions.isError ? <ErrorState title="جلسه‌های اجرا قابل دریافت نیستند" error={sessions.error} retry={() => void sessions.refetch()} /> : !sessions.data?.length ? <p className="pipeline-picker-empty">این اجرا هنوز جلسه‌ای ندارد.</p> : <PipelineSessionPicker sessions={sessions.data} selectedId={sessionId} onSelect={selectSession} />)}
        {sessionId && sessions.data && !sessionExists && <div className="pipeline-inline-error"><WarningCircle /><span>جلسه در اجرای انتخاب‌شده موجود نیست. نخستین جلسه معتبر انتخاب می‌شود.</span></div>}
        {sessionExists && (detail.isLoading ? <div className="pipeline-picker-loading"><SkeletonRows count={3} /></div> : detail.isError ? <ErrorState title="جزئیات جلسه قابل دریافت نیست" error={detail.error} retry={() => void detail.refetch()} /> : !detail.data?.turns.length ? <p className="pipeline-picker-empty">این جلسه هنوز نوبتی ندارد.</p> : <PipelineTurnPicker turns={detail.data.turns} selectedId={turnId} divergentTurn={selectedSession?.first_divergent_turn} onSelect={selectTurn} />)}
      </aside>
      <section className="pipeline-investigation">
        {!runId ? <EmptyState title="یک اجرا را انتخاب کنید" message="آخرین اجراها در Trace Locator نمایش داده شده‌اند. هیچ trace تا زمان انتخاب اجرا بارگذاری نمی‌شود." /> : !runExists ? <EmptyState title="اجرای درخواستی پیدا نشد" message="یک اجرای موجود را از Trace Locator انتخاب کنید." /> : <>
          {selectedRun.isLoading ? <section className="surface pipeline-loading"><SkeletonRows count={3} /></section> : selectedRun.isError ? <ErrorState title="اطلاعات اجرا قابل دریافت نیست" error={selectedRun.error} retry={() => void selectedRun.refetch()} /> : selectedRun.data && <RunContext run={selectedRun.data} onOpen={() => onUrlChange({ panel: "runs", runId: selectedRun.data!.id, sessionId: null, turnId: null, stage: null })} />}
          {!sessionId ? <EmptyState title="جلسه‌ای انتخاب نشده است" message="برای دیدن نوبت‌ها، یک جلسه یا تکرار را انتخاب کنید." /> : !turnId ? <EmptyState title="نوبتی انتخاب نشده است" message="برای بارگذاری trace فقط یک نوبت را انتخاب کنید." /> : <TurnTrace turnId={turnId} divergentStage={selectedSession?.first_divergent_turn === selectedTurn?.turn_index ? selectedSession?.first_divergent_stage : null} selectedStage={stage || "NORMALIZATION"} onStageSelect={selectStage} />}
        </>}
      </section>
    </div>}
  </main>;
}

function RunContext({ run, onOpen }: { run: Run; onOpen: () => void }) {
  return <section className="pipeline-run-context surface">
    <div className="pipeline-run-context__identity"><div><span dir="ltr">{run.run_type}</span><strong dir="ltr" title={run.id}>{run.id}</strong></div><StatusBadge status={run.status} /><Button variant="secondary" onClick={onOpen}><ArrowSquareOut />باز کردن اجرای کامل</Button></div>
    <dl><div><dt>Git SHA</dt><dd><code dir="ltr" title={run.git_commit_sha || ""}>{shortHash(run.git_commit_sha)}</code></dd></div><div><dt>جلسه‌ها</dt><dd dir="ltr">{run.completed_sessions} / {run.total_sessions}</dd></div><div><dt>نوبت‌ها</dt><dd dir="ltr">{run.completed_turns} / {run.total_turns}</dd></div><div><dt>Fallback</dt><dd>{run.fallback_count}</dd></div><div><dt>خطا</dt><dd>{run.error_count}</dd></div><div><dt>زیرساخت</dt><dd>{run.infrastructure_error_count}</dd></div></dl>
    <div className="pipeline-run-context__time"><span>ایجاد: {formatDate(run.created_at)}</span><span>شروع: {formatDate(run.started_at)}</span><span>پایان: {formatDate(run.finished_at)}</span></div>
  </section>;
}
