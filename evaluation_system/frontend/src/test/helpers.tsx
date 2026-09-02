import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, PropsWithChildren } from "react";
import { AuthProvider } from "../app/auth";
import type { RunSession, TurnTrace } from "../types/api";

export function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

export function renderWithProviders(element: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  function Wrapper({ children }: PropsWithChildren) { return <QueryClientProvider client={client}><AuthProvider>{children}</AuthProvider></QueryClientProvider>; }
  return render(element, { wrapper: Wrapper, ...options });
}

export const runSessionFixture: RunSession = {
  id: "run-session-1", run_id: "run-1", dataset_session_id: "dataset-session-1", source_session_id: "458923", repeat_index: 1,
  evaluation_session_key: "eval-key", status: "COMPLETED", turn_count: 1, fallback_count: 0, error_count: 0, infrastructure_error_count: 0,
  total_latency_ms: 1234, first_divergent_turn: null, first_divergent_stage: null, first_query: "افتتاح حساب چطور است؟", synthetic_session: false,
  synthetic_label: null, started_at: "2026-08-31T10:00:00Z", finished_at: "2026-08-31T10:00:02Z", metadata: {},
};

export function traceFixture(overrides: Partial<TurnTrace["turn"]> = {}, suffix = "a"): TurnTrace {
  const turn = {
    id: `turn-${suffix}`, turn_index: 1, raw_query: "افتتاح حساب چطور است؟", normalized_query: "افتتاح حساب چطور است؟",
    rewritten_query: "روش افتتاح حساب", history_before_hash: `history-before-${suffix}`, history_after_hash: `history-after-${suffix}`,
    actual_intent: "general", intent_score: .94, selected_context_hash: `context-${suffix}`, actual_answer: `پاسخ ${suffix}`,
    fallback_used: false, fallback_reason: null, status: "COMPLETED", infrastructure_error: false, error_code: null,
    total_latency_ms: 1200, started_at: "2026-08-31T10:00:00Z", finished_at: "2026-08-31T10:00:02Z", ...overrides,
  };
  const names = ["NORMALIZATION", "INTENT", "REWRITE", "RETRIEVAL", "RERANK", "CONTEXT_SELECTION", "PROMPT_BUILD", "GENERATION"] as const;
  return { turn, stages: names.map((name, index) => ({
    stage_name: name, stage_order: (index + 1) * 10, status: name === "RERANK" ? "SKIPPED" : "COMPLETED",
    input_hash: `in-${name}-${suffix}`, output_hash: `out-${name}-${suffix}`, duration_ms: 10 + index,
    input_data: name === "REWRITE" ? { original_query: turn.normalized_query, history_used: "[بدون مکالمه قبلی]" } : name === "CONTEXT_SELECTION" ? { history_messages: [] } : {},
    output_data: name === "NORMALIZATION" ? { normalized_query: turn.normalized_query } : name === "INTENT" ? { label: turn.actual_intent, score: turn.intent_score } : name === "REWRITE" ? { rewritten_query: turn.rewritten_query } : name === "RETRIEVAL" ? { candidates: [{ rank: 1, chunk_id: `chunk-${suffix}`, retrieval_score: .88, content: "محتوای بانکی", title: "افتتاح حساب" }] } : name === "CONTEXT_SELECTION" ? { selected_chunk_ids: [`chunk-${suffix}`], selected_context: "زمینه دقیق" } : name === "PROMPT_BUILD" ? { prompt: "پرامپت دقیق" } : name === "GENERATION" ? { answer: turn.actual_answer } : {},
    metrics: name === "INTENT" ? { effective_threshold: .875 } : name === "GENERATION" ? { settings: { model: "/app/model", temperature: 1 }, fallback_used: turn.fallback_used, fallback_reason: turn.fallback_reason } : {},
    error_code: null, error_data: null,
  })) };
}
