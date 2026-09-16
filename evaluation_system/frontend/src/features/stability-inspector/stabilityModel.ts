import type { RunSession, RunTurn, StageName, StabilitySummary, TurnTrace } from "../../types/api";

export interface LoadedAttempt {
  session: RunSession;
  turn: RunTurn;
  trace: TurnTrace | null;
  traceError: unknown | null;
}

export type MatrixState = "baseline" | "same" | "different" | "error" | "unavailable";

export function logicalKey(session: RunSession): string {
  return session.dataset_session_id || session.source_session_id || session.synthetic_label || session.id;
}

export function canonicalSummary(sessions: RunSession[]): StabilitySummary | undefined {
  return sessions.find((item) => item.metadata.stability)?.metadata.stability;
}

export function stageHash(trace: TurnTrace | null | undefined, stage: StageName): string | null {
  return trace?.stages.find((item) => item.stage_name === stage)?.output_hash || null;
}

function traceFingerprint(trace: TurnTrace): string {
  const turn = trace.turn;
  return JSON.stringify({
    normalized_query: turn.normalized_query,
    history_before_hash: turn.history_before_hash,
    rewritten_query: turn.rewritten_query,
    intent: turn.actual_intent,
    intent_score: turn.intent_score,
    selected_context_hash: turn.selected_context_hash,
    answer: turn.actual_answer,
    fallback: turn.fallback_used,
    error: turn.error_code,
    stages: trace.stages.map((stage) => [stage.stage_name, stage.status, stage.output_hash]),
  });
}

export function matrixState(attempt: LoadedAttempt | undefined, baseline: LoadedAttempt | undefined, isBaseline: boolean): MatrixState {
  if (!attempt || attempt.traceError || attempt.turn.status === "ERROR" || attempt.turn.infrastructure_error) return attempt?.traceError || attempt?.turn.status === "ERROR" || attempt?.turn.infrastructure_error ? "error" : "unavailable";
  if (!attempt.trace) return "unavailable";
  if (attempt.trace.stages.some((stage) => stage.status === "ERROR")) return "error";
  if (isBaseline) return "baseline";
  if (!baseline?.trace || baseline.traceError || baseline.turn.status === "ERROR") return "unavailable";
  return traceFingerprint(attempt.trace) === traceFingerprint(baseline.trace) ? "same" : "different";
}

export async function mapWithConcurrency<T, R>(values: T[], limit: number, task: (value: T) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(values.length);
  let cursor = 0;
  async function worker() {
    while (cursor < values.length) {
      const index = cursor++;
      results[index] = await task(values[index]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, values.length) }, worker));
  return results;
}
