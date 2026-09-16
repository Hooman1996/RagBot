import { ArrowSquareOut, ArrowsLeftRight, Fingerprint, MagnifyingGlass } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { STAGES } from "../../components/trace/StageRail";
import { TurnTrace } from "../../components/trace/TurnTrace";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { formatDuration, shortHash } from "../../components/ui/format";
import type { RunSession, StageName, TurnTrace as TurnTraceType } from "../../types/api";
import { canonicalSummary, stageHash, type LoadedAttempt } from "./stabilityModel";

function valueState(left: unknown, right: unknown): "same" | "different" | "unavailable" {
  if (left == null || right == null || left === "" || right === "") return "unavailable";
  return JSON.stringify(left) === JSON.stringify(right) ? "same" : "different";
}

function Value({ value, multiline = false }: { value: unknown; multiline?: boolean }) {
  const text = value == null || value === "" ? "ناموجود" : String(value);
  return multiline ? <p dir="auto">{text}</p> : <code dir="ltr" title={text}>{text}</code>;
}

function AnswerPane({ label, trace }: { label: string; trace: TurnTraceType | null }) {
  return <article className="answer-pane"><header><strong dir="ltr">{label}</strong>{trace?.turn.status && <Badge tone={trace.turn.status === "ERROR" ? "danger" : "neutral"}>{trace.turn.status}</Badge>}</header><div className="answer-content" dir="auto">{trace?.turn.actual_answer || "پاسخی در trace ثبت نشده است."}</div><dl><div><dt>Output hash</dt><dd dir="ltr">{shortHash(stageHash(trace, "GENERATION"))}</dd></div><div><dt>Fallback</dt><dd>{trace ? (trace.turn.fallback_used ? "بله" : "خیر") : "-"}</dd></div><div><dt>Latency</dt><dd dir="ltr">{formatDuration(trace?.turn.total_latency_ms)}</dd></div><div><dt>Error</dt><dd dir="ltr">{trace?.turn.error_code || "-"}</dd></div></dl></article>;
}

export function StabilityComparison({ sessions, attempts, selectedTurn, onPipelineOpen }: { sessions: RunSession[]; attempts: LoadedAttempt[]; selectedTurn: number; onPipelineOpen?: (sessionId: string, turnId: string, stage: StageName) => void }) {
  const repeats = useMemo(() => [...new Set(sessions.map((item) => item.repeat_index))].sort((a, b) => a - b), [sessions]);
  const [left, setLeft] = useState(repeats[0] || 1);
  const [right, setRight] = useState(repeats[1] || repeats[0] || 1);
  const [traceOpen, setTraceOpen] = useState<"left" | "right" | null>(null);
  useEffect(() => { if (!repeats.includes(left)) setLeft(repeats[0] || 1); if (!repeats.includes(right)) setRight(repeats[1] || repeats[0] || 1); }, [repeats, left, right]);
  const findAttempt = (repeat: number) => attempts.find((item) => item.session.repeat_index === repeat && item.turn.turn_index === selectedTurn);
  const leftAttempt = findAttempt(left); const rightAttempt = findAttempt(right);
  const leftTrace = leftAttempt?.trace || null; const rightTrace = rightAttempt?.trace || null;
  const summary = canonicalSummary(sessions);
  const errorValue = (attempt: LoadedAttempt | undefined) => !attempt ? null : attempt.traceError ? "TRACE_UNAVAILABLE" : attempt.trace?.turn.error_code || "NO_ERROR";
  const fields = [
    ["Normalized query", leftTrace?.turn.normalized_query, rightTrace?.turn.normalized_query, true],
    ["History hash", leftTrace?.turn.history_before_hash, rightTrace?.turn.history_before_hash],
    ["Rewritten query", leftTrace?.turn.rewritten_query, rightTrace?.turn.rewritten_query, true],
    ["Intent", leftTrace?.turn.actual_intent, rightTrace?.turn.actual_intent],
    ["Intent score", leftTrace?.turn.intent_score, rightTrace?.turn.intent_score],
    ["Retrieval output hash", stageHash(leftTrace, "RETRIEVAL"), stageHash(rightTrace, "RETRIEVAL")],
    ["Rerank output hash", stageHash(leftTrace, "RERANK"), stageHash(rightTrace, "RERANK")],
    ["Selected context hash", leftTrace?.turn.selected_context_hash, rightTrace?.turn.selected_context_hash],
    ["Prompt output hash", stageHash(leftTrace, "PROMPT_BUILD"), stageHash(rightTrace, "PROMPT_BUILD")],
    ["Generation output hash", stageHash(leftTrace, "GENERATION"), stageHash(rightTrace, "GENERATION")],
    ["Fallback state", leftTrace?.turn.fallback_used, rightTrace?.turn.fallback_used],
    ["Error state", errorValue(leftAttempt), errorValue(rightAttempt)],
    ["Latency", leftTrace?.turn.total_latency_ms, rightTrace?.turn.total_latency_ms],
  ] as const;
  const canonicalStage = summary?.first_divergent_stage || "NORMALIZATION";
  const traceForOpen = traceOpen === "left" ? leftAttempt : traceOpen === "right" ? rightAttempt : null;

  return <section className="stability-comparison surface" aria-labelledby="comparison-title">
    <div className="comparison-toolbar"><div><h2 id="comparison-title">مقایسه A/B نوبت {selectedTurn}</h2><p>مقادیر اجرایی واقعی نمایش داده می‌شوند، بدون داوری بهتر یا بدتر.</p></div><div className="repeat-selectors"><label>A<select aria-label="تکرار A" value={left} onChange={(event) => setLeft(Number(event.target.value))}>{repeats.map((value) => <option key={value} value={value}>Repeat {value}</option>)}</select></label><ArrowsLeftRight aria-hidden="true" /><label>B<select aria-label="تکرار B" value={right} onChange={(event) => setRight(Number(event.target.value))}>{repeats.map((value) => <option key={value} value={value}>Repeat {value}</option>)}</select></label></div></div>
    <div className={`divergence-callout ${summary?.first_divergent_turn ? "is-diverged" : "is-stable"}`}><Fingerprint size={20} /><div><strong>{summary?.first_divergent_turn ? `اولین واگرایی: نوبت ${summary.first_divergent_turn}` : "واگرایی canonical ثبت نشده است"}</strong><span dir="ltr">{summary?.first_divergent_stage ? `First stage: ${summary.first_divergent_stage}` : "First stage: unavailable"}</span></div></div>
    {(!leftTrace || !rightTrace) && <div className="comparison-unavailable"><MagnifyingGlass /><span>trace یکی از تکرارها برای این نوبت موجود نیست. داده مفقود به عنوان واگرایی محاسبه نمی‌شود.</span></div>}
    <div className="pipeline-difference" role="table" aria-label="ماتریس تفاوت مراحل"><div className="pipeline-difference__head" role="row"><span>مرحله</span><span>Repeat A</span><span>وضعیت</span><span>Repeat B</span></div>{STAGES.map(({ name, label }) => { const a = stageHash(leftTrace, name); const b = stageHash(rightTrace, name); const state = valueState(a, b); const first = summary?.first_divergent_turn === selectedTurn && summary.first_divergent_stage === name; return <div className={`pipeline-difference__row is-${state} ${first ? "is-first" : ""}`} role="row" key={name}><span>{label}{first && <Badge tone="diverged">اولین واگرایی</Badge>}</span><code dir="ltr" title={a || ""}>{shortHash(a)}</code><strong>{state === "same" ? "SAME" : state === "different" ? "DIFFERENT" : "UNAVAILABLE"}</strong><code dir="ltr" title={b || ""}>{shortHash(b)}</code></div>; })}</div>
    <div className="value-comparison"><div className="value-comparison__head"><span>مقدار</span><span>Repeat A</span><span>Repeat B</span></div>{fields.map(([label, a, b, multiline]) => { const state = valueState(a, b); return <div key={label} className={`value-row is-${state}`}><strong>{label}</strong><Value value={a} multiline={multiline} /><Value value={b} multiline={multiline} /></div>; })}</div>
    <div className="answer-comparison"><AnswerPane label={`Repeat ${left}`} trace={leftTrace} /><AnswerPane label={`Repeat ${right}`} trace={rightTrace} /></div>
    <div className="trace-actions"><Button variant="secondary" disabled={!leftTrace} onClick={() => setTraceOpen(traceOpen === "left" ? null : "left")}><MagnifyingGlass />Inspect Repeat A trace</Button><Button variant="secondary" disabled={!rightTrace} onClick={() => setTraceOpen(traceOpen === "right" ? null : "right")}><MagnifyingGlass />Inspect Repeat B trace</Button>{onPipelineOpen && leftAttempt?.trace && <Button variant="ghost" onClick={() => onPipelineOpen(leftAttempt.session.id, leftAttempt.turn.id, canonicalStage)}><ArrowSquareOut />Open in Pipeline</Button>}</div>
    {traceForOpen?.trace && <div className="comparison-trace"><TurnTrace turnId={traceForOpen.turn.id} initialTrace={traceForOpen.trace} divergentStage={summary?.first_divergent_turn === selectedTurn ? summary.first_divergent_stage : null} /></div>}
  </section>;
}
