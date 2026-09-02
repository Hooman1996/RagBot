import { ArrowsLeftRight, CaretDown, CaretLeft, Fingerprint, Scales } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { Fragment, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { RunProgress } from "../../components/runs/RunProgress";
import { TurnTrace } from "../../components/trace/TurnTrace";
import { STAGES } from "../../components/trace/StageRail";
import { Badge, statusTone } from "../../components/ui/Badge";
import { EmptyState, ErrorState, SkeletonRows } from "../../components/ui/States";
import { formatDuration, shortHash } from "../../components/ui/format";
import type { RunSession, StageName, TurnTrace as TurnTraceType } from "../../types/api";

interface LoadedAttempt { session: RunSession; trace: TurnTraceType }

function logicalKey(session: RunSession): string {
  return session.dataset_session_id || session.source_session_id || session.synthetic_label || session.id;
}

function stageHash(trace: TurnTraceType, stage: StageName): string | null {
  return trace.stages.find((item) => item.stage_name === stage)?.output_hash || null;
}

function canonicalSummary(sessions: RunSession[]) {
  const value = sessions.find((item) => item.metadata.stability)?.metadata.stability;
  return value;
}

function Comparison({ attempts, sessions }: { attempts: LoadedAttempt[]; sessions: RunSession[] }) {
  const repeats = [...new Set(sessions.map((item) => item.repeat_index))].sort((a, b) => a - b);
  const [left, setLeft] = useState(repeats[0] || 1); const [right, setRight] = useState(repeats[1] || repeats[0] || 1);
  const summary = canonicalSummary(sessions);
  const leftAttempts = attempts.filter((item) => item.session.repeat_index === left).sort((a, b) => a.trace.turn.turn_index - b.trace.turn.turn_index);
  const rightAttempts = attempts.filter((item) => item.session.repeat_index === right).sort((a, b) => a.trace.turn.turn_index - b.trace.turn.turn_index);
  return <section className="comparison"><div className="comparison__head"><div><Scales size={23} /><div><h3>مقایسه دو تکرار</h3><p>مرحله نخست واگرا از تحلیل بک‌اند مرجع است.</p></div></div><div><label>تکرار راست<select value={left} onChange={(event) => setLeft(Number(event.target.value))}>{repeats.map((value) => <option key={value}>{value}</option>)}</select></label><ArrowsLeftRight /><label>تکرار چپ<select value={right} onChange={(event) => setRight(Number(event.target.value))}>{repeats.map((value) => <option key={value}>{value}</option>)}</select></label></div></div>
    <div className={`divergence-callout ${summary?.first_divergent_turn ? "is-diverged" : "is-stable"}`}><Fingerprint size={19} /><div><strong>{summary?.first_divergent_turn ? `Diverged at turn ${summary.first_divergent_turn}` : "Stable across selected repetitions"}</strong><span>{summary?.first_divergent_stage ? `Canonical first stage: ${summary.first_divergent_stage}` : "No exact-output divergence recorded"}</span></div></div>
    <div className="comparison-grid"><div className="comparison-title">مرحله</div><div className="comparison-title">Repeat {left}</div><div className="comparison-title">Repeat {right}</div>{leftAttempts.map((attempt, index) => {
      const peer = rightAttempts[index]; const turn = attempt.trace.turn.turn_index;
      return <div className="comparison-turn" key={turn}><h4>نوبت {turn}</h4>{STAGES.map(({ name, label }) => {
        const leftHash = stageHash(attempt.trace, name); const rightHash = peer ? stageHash(peer.trace, name) : null; const same = leftHash === rightHash;
        const canonical = summary?.first_divergent_turn === turn && summary.first_divergent_stage === name;
        return <div className={`comparison-row ${canonical ? "is-first" : ""}`} key={name}><span>{label}{canonical && <Badge tone="diverged">اولین واگرایی</Badge>}</span><code dir="ltr">{shortHash(leftHash)}</code><span className={same ? "same" : "different"}>{same ? "SAME" : "DIVERGED"}</span><code dir="ltr">{shortHash(rightHash)}</code></div>;
      })}</div>;
    })}</div>
  </section>;
}

function TurnAggregate({ turn, attempts, sessions }: { turn: number; attempts: LoadedAttempt[]; sessions: RunSession[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const summary = canonicalSummary(sessions);
  const rows = attempts.filter((item) => item.trace.turn.turn_index === turn).sort((a, b) => a.session.repeat_index - b.session.repeat_index);
  const variants = (selector: (attempt: LoadedAttempt) => unknown) => new Set(rows.map((item) => JSON.stringify(selector(item)))).size;
  const counts: Record<string, number> = {
    normalization: variants((item) => item.trace.turn.normalized_query), intent: variants((item) => item.trace.turn.actual_intent), rewrite: variants((item) => item.trace.turn.rewritten_query),
    retrieval: variants((item) => stageHash(item.trace, "RETRIEVAL")), rerank: variants((item) => stageHash(item.trace, "RERANK")), context: variants((item) => item.trace.turn.selected_context_hash),
    prompt: variants((item) => stageHash(item.trace, "PROMPT_BUILD")), answer: variants((item) => stageHash(item.trace, "GENERATION")),
  };
  const labels: Record<string, string> = { normalization: "Normalization", intent: "Intent", rewrite: "Rewrite", retrieval: "Retrieval", rerank: "Rerank", context: "Context", prompt: "Prompt", answer: "Answer" };
  return <section className="turn-aggregate"><div className="turn-aggregate__head"><h3>نوبت {turn}</h3>{summary?.first_divergent_turn === turn && <Badge tone="diverged">اولین نوبت واگرا</Badge>}</div><dl className="variant-grid">{Object.entries(counts).map(([key, value]) => <div className={value === 1 ? "is-stable" : "is-diverged"} key={key}><dt>{labels[key]}</dt><dd>{value}</dd><span>{value === 1 ? "Stable" : "Diverged"}</span></div>)}</dl>
    <div className="table-wrap"><table className="data-table compact"><thead><tr><th>Repeat</th><th>Intent</th><th>Rewrite</th><th>Top chunk</th><th>Context</th><th>Prompt</th><th>Answer</th><th>Fallback</th><th>مدت</th><th></th></tr></thead><tbody>{rows.map(({ session, trace }) => {
      const retrieval = trace.stages.find((stage) => stage.stage_name === "RETRIEVAL"); const candidates = Array.isArray(retrieval?.output_data?.candidates) ? retrieval.output_data.candidates : [];
      const rowOpen = open === trace.turn.id;
      return <Fragment key={trace.turn.id}><tr><td>{session.repeat_index}</td><td>{trace.turn.actual_intent || "-"}</td><td><code dir="ltr">{shortHash(stageHash(trace, "REWRITE"))}</code></td><td dir="ltr">{String((candidates[0] as Record<string, unknown> | undefined)?.chunk_id ?? "-")}</td><td><code dir="ltr">{shortHash(trace.turn.selected_context_hash)}</code></td><td><code dir="ltr">{shortHash(stageHash(trace, "PROMPT_BUILD"))}</code></td><td><code dir="ltr">{shortHash(stageHash(trace, "GENERATION"))}</code></td><td>{trace.turn.fallback_used ? <Badge tone="warning">Fallback</Badge> : "-"}</td><td>{formatDuration(trace.turn.total_latency_ms)}</td><td><button className="icon-button" aria-label="باز کردن تلاش" onClick={() => setOpen(rowOpen ? null : trace.turn.id)}>{rowOpen ? <CaretDown /> : <CaretLeft />}</button></td></tr>{rowOpen && <tr className="expanded-row"><td colSpan={10}><TurnTrace turnId={trace.turn.id} initialTrace={trace} divergentStage={summary?.first_divergent_turn === turn ? summary.first_divergent_stage : null} /></td></tr>}</Fragment>;
    })}</tbody></table></div>
  </section>;
}

function StabilitySession({ sessions }: { sessions: RunSession[] }) {
  const { api } = useAuth(); const [open, setOpen] = useState(false);
  const summary = canonicalSummary(sessions); const exemplar = sessions[0];
  const attempts = useQuery({
    queryKey: ["stability-attempts", ...sessions.map((item) => item.id)], enabled: open,
    queryFn: async () => {
      const details = await Promise.all(sessions.map(async (session) => ({ session, detail: await api.runSession(session.id) })));
      const pairs = details.flatMap(({ session, detail }) => detail.turns.map((turn) => ({ session, turn })));
      return Promise.all(pairs.map(async ({ session, turn }) => ({ session, trace: await api.turnTrace(turn.id) })));
    },
  });
  const fallbackCount = sessions.reduce((sum, item) => sum + item.fallback_count, 0); const totalTurns = sessions.reduce((sum, item) => sum + item.turn_count, 0);
  const turnNumbers = attempts.data ? [...new Set(attempts.data.map((item) => item.trace.turn.turn_index))].sort((a, b) => a - b) : [];
  return <article className={`stability-session ${open ? "is-open" : ""}`}><button className="stability-session__head" onClick={() => setOpen(!open)} aria-expanded={open}><span>{open ? <CaretDown /> : <CaretLeft />}</span><div><strong dir="auto">{exemplar.source_session_id || exemplar.synthetic_label || "جلسه دستی"}</strong><small dir="auto">{exemplar.first_query || "-"}</small></div><dl><div><dt>تکرار</dt><dd>{sessions.length}</dd></div><div><dt>نوبت</dt><dd>{exemplar.turn_count}</dd></div><div><dt>Fallback rate</dt><dd>{totalTurns ? `${Math.round(fallbackCount / totalTurns * 100)}%` : "-"}</dd></div><div><dt>پاسخ یکتا</dt><dd>{summary?.variant_counts.answer ?? "-"}</dd></div><div><dt>بازنویسی یکتا</dt><dd>{summary?.variant_counts.rewrite ?? "-"}</dd></div><div><dt>زمینه یکتا</dt><dd>{summary?.variant_counts.context ?? "-"}</dd></div><div><dt>اولین واگرایی</dt><dd>{summary?.first_divergent_turn ? `نوبت ${summary.first_divergent_turn} / ${summary.first_divergent_stage}` : "Stable"}</dd></div></dl></button>
    {open && <div className="stability-session__body">{attempts.isLoading ? <SkeletonRows count={6} /> : attempts.isError ? <ErrorState title="تلاش‌ها قابل دریافت نیستند" error={attempts.error} retry={() => void attempts.refetch()} /> : <><Comparison attempts={attempts.data!} sessions={sessions} />{turnNumbers.map((turn) => <TurnAggregate key={turn} turn={turn} attempts={attempts.data!} sessions={sessions} />)}</>}</div>}
  </article>;
}

export function StabilityResults({ runId }: { runId: string }) {
  const { api } = useAuth();
  const sessions = useQuery({ queryKey: ["run-sessions", runId], queryFn: () => api.runSessions(runId), refetchInterval: 5_000 });
  const groups = useMemo(() => {
    const map = new Map<string, RunSession[]>();
    for (const session of sessions.data || []) map.set(logicalKey(session), [...(map.get(logicalKey(session)) || []), session]);
    return [...map.values()];
  }, [sessions.data]);
  return <div className="run-results"><RunProgress runId={runId} /><div className="section-heading"><div><h2>پایداری نشست‌ها</h2><p>تفاوت متن به معنی خطا نیست. اولین مرحله واگرا از محاسبه پایدار بک‌اند می‌آید.</p></div></div>{sessions.isLoading ? <SkeletonRows count={5} /> : sessions.isError ? <ErrorState error={sessions.error} retry={() => void sessions.refetch()} /> : groups.length ? groups.map((group) => <StabilitySession key={logicalKey(group[0])} sessions={group} />) : <EmptyState title="هنوز تکراری تکمیل نشده است" message="پس از تکمیل نخستین جلسه، مقایسه در این بخش ظاهر می‌شود." />}</div>;
}
