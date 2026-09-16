import { ArrowSquareOut, CaretLeft, Fingerprint, WarningCircle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useEvaluationApi } from "../../api/context";
import { RunProgress } from "../../components/runs/RunProgress";
import { PageHeader } from "../../components/shell/PageHeader";
import { Badge, statusTone } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { EmptyState, ErrorState, SkeletonRows } from "../../components/ui/States";
import type { RunSession, StageName } from "../../types/api";
import { StabilityComparison } from "./StabilityComparison";
import { StabilityMatrix } from "./StabilityMatrix";
import { canonicalSummary, logicalKey, mapWithConcurrency, type LoadedAttempt } from "./stabilityModel";

function GroupButton({ sessions, selected, onSelect }: { sessions: RunSession[]; selected: boolean; onSelect: () => void }) {
  const exemplar = sessions[0]; const summary = canonicalSummary(sessions);
  const fallbackCount = summary?.fallback_count ?? sessions.reduce((sum, item) => sum + item.fallback_count, 0);
  const totalTurns = sessions.reduce((sum, item) => sum + item.turn_count, 0);
  const fallbackRate = summary?.fallback_rate ?? (totalTurns ? fallbackCount / totalTurns : 0);
  const incomparable = summary?.incomparable_turn_count;
  const label = exemplar.source_session_id || exemplar.synthetic_label || exemplar.dataset_session_id || `Session ${exemplar.id.slice(0, 8)}`;
  return <button type="button" className={`stability-group ${selected ? "is-selected" : ""}`} onClick={onSelect} aria-pressed={selected}>
    <div className="stability-group__identity"><span><Fingerprint size={17} /><strong dir="auto">{label}</strong></span><small dir="auto">{exemplar.first_query || "پرسش نخست در خلاصه اجرا موجود نیست"}</small></div>
    <dl><div><dt>تکرار</dt><dd>{sessions.length}</dd></div><div><dt>نوبت</dt><dd>{Math.max(...sessions.map((item) => item.turn_count))}</dd></div><div><dt>Fallback</dt><dd dir="ltr">{fallbackCount} / {Math.round(fallbackRate * 100)}%</dd></div>{incomparable != null && <div><dt>غیرقابل مقایسه</dt><dd>{incomparable}</dd></div>}<div><dt>پاسخ یکتا</dt><dd>{summary?.variant_counts.answer ?? "-"}</dd></div><div><dt>بازنویسی یکتا</dt><dd>{summary?.variant_counts.rewrite ?? "-"}</dd></div><div><dt>زمینه یکتا</dt><dd>{summary?.variant_counts.context ?? "-"}</dd></div><div><dt>اولین واگرایی</dt><dd>{summary?.first_divergent_turn ? `${summary.first_divergent_turn} / ${summary.first_divergent_stage || "-"}` : "ثبت نشده"}</dd></div></dl>
    <CaretLeft size={18} aria-hidden="true" />
  </button>;
}

export function StabilityResults({ runId, onRunInspect, onPipelineOpen }: { runId: string; onRunInspect?: (id: string) => void; onPipelineOpen?: (sessionId: string, turnId: string, stage: StageName) => void }) {
  const api = useEvaluationApi();
  const sessions = useQuery({ queryKey: ["run-sessions", runId], queryFn: () => api.runSessions(runId), refetchInterval: 5_000 });
  const groups = useMemo(() => {
    const map = new Map<string, RunSession[]>();
    for (const session of sessions.data || []) map.set(logicalKey(session), [...(map.get(logicalKey(session)) || []), session]);
    return [...map.entries()].map(([key, values]) => ({ key, sessions: values.sort((a, b) => a.repeat_index - b.repeat_index) }));
  }, [sessions.data]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedTurn, setSelectedTurn] = useState(1);
  useEffect(() => { if (groups.length && !groups.some((group) => group.key === selectedKey)) setSelectedKey(groups[0].key); }, [groups, selectedKey]);
  const selected = groups.find((group) => group.key === selectedKey) || groups[0] || null;
  const details = useQuery({
    queryKey: ["stability-group-details", runId, selected?.key || null], enabled: !!selected,
    queryFn: async () => {
      const sessionDetails = await mapWithConcurrency(selected!.sessions, 5, async (session) => {
        try { return { session, detail: await api.runSession(session.id), error: null }; } catch (error) { return { session, detail: null, error }; }
      });
      const work = sessionDetails.flatMap(({ session, detail }) => (detail?.turns || []).map((turn) => ({ session, turn })));
      return mapWithConcurrency(work, 5, async ({ session, turn }): Promise<LoadedAttempt> => {
        try { return { session, turn, trace: await api.turnTrace(turn.id), traceError: null }; } catch (error) { return { session, turn, trace: null, traceError: error }; }
      });
    },
  });
  const selectedSummary = selected ? canonicalSummary(selected.sessions) : undefined;
  const selectedStillRunning = selected?.sessions.some((session) => session.status === "PENDING" || session.status === "RUNNING");

  return <div className="stability-results-page">
    <PageHeader title="تحلیل اجرای پایداری" description="نشست منطقی را انتخاب کنید، ماتریس تکرارها را بخوانید و دو اجرای مستقل را بدون داوری کیفیت مقایسه کنید." meta={<div className="page-header-actions"><code dir="ltr" title={runId}>{runId.slice(0, 12)}</code>{onRunInspect && <Button variant="secondary" onClick={() => onRunInspect(runId)}><ArrowSquareOut />Open full Run Inspector</Button>}</div>} />
    <RunProgress runId={runId} />
    {sessions.isLoading ? <SkeletonRows count={6} /> : sessions.isError ? <ErrorState title="نشست‌های اجرای پایداری دریافت نشدند" error={sessions.error} retry={() => void sessions.refetch()} /> : !groups.length ? <EmptyState title="هنوز تکراری در دسترس نیست" message="ممکن است اجرا در صف باشد. خلاصه نشست‌ها پس از ثبت نخستین تکرار نمایش داده می‌شود." /> : <div className="stability-workspace">
      <aside className="stability-group-list" aria-label="نشست‌های منطقی"><header><h2>نشست‌ها و پرسش‌ها</h2><Badge tone="neutral">{groups.length.toLocaleString("fa-IR")}</Badge></header>{groups.map((group) => <GroupButton key={group.key} sessions={group.sessions} selected={group.key === selected?.key} onSelect={() => { setSelectedKey(group.key); setSelectedTurn(1); }} />)}</aside>
      <main className="stability-analysis">
        {selectedStillRunning && <div className="stability-running-note"><WarningCircle /><span>این گروه هنوز کامل نشده است. سلول‌های فاقد trace تا زمان ثبت داده «ناموجود» می‌مانند.</span></div>}
        {selectedSummary?.incomparable_turn_count ? <div className="stability-running-note"><WarningCircle /><span>{selectedSummary.incomparable_turn_count.toLocaleString("fa-IR")} نوبت طبق خلاصه بک‌اند غیرقابل مقایسه است.</span></div> : null}
        {details.isLoading ? <div className="stability-detail-loading"><SkeletonRows count={7} /><p>جزئیات فقط برای گروه انتخاب‌شده بارگذاری می‌شوند.</p></div> : details.isError ? <ErrorState title="جزئیات گروه انتخاب‌شده دریافت نشد" error={details.error} retry={() => void details.refetch()} /> : <>
          <StabilityMatrix sessions={selected!.sessions} attempts={details.data || []} selectedTurn={selectedTurn} onTurnSelect={setSelectedTurn} />
          <StabilityComparison sessions={selected!.sessions} attempts={details.data || []} selectedTurn={selectedTurn} onPipelineOpen={onPipelineOpen} />
        </>}
      </main>
    </div>}
  </div>;
}
