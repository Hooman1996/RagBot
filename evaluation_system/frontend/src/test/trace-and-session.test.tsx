import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SessionTable } from "../components/session-results/SessionTable";
import { TurnTrace } from "../components/trace/TurnTrace";
import { renderWithProviders, jsonResponse, runSessionFixture, traceFixture } from "./helpers";

it("expands a session, turn, and shared trace inspector", async () => {
  const trace = traceFixture();
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/run-sessions/run-session-1")) return jsonResponse({ id: "run-session-1", status: "COMPLETED", repeat_index: 1, turns: [{ id: "turn-a", turn_index: 1, raw_query: trace.turn.raw_query, actual_answer: trace.turn.actual_answer, actual_intent: "general", rewritten_query: "روش افتتاح حساب", fallback_used: false, fallback_reason: null, status: "COMPLETED", infrastructure_error: false, error_code: null, total_latency_ms: 1200 }] });
    if (url.endsWith("/datasets/sessions/dataset-session-1/turns")) return jsonResponse([{ id: "source-turn", turn_index: 1, source_row_number: 2, source_time_raw: null, source_timestamp: null, query: trace.turn.raw_query, metadata: {} }]);
    if (url.endsWith("/run-turns/turn-a/trace")) return jsonResponse(trace);
    return jsonResponse([]);
  }));
  renderWithProviders(<SessionTable sessions={[runSessionFixture]} />); const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "باز کردن جلسه" }));
  expect(await screen.findByText("پاسخ a")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /نوبت 1/ }));
  expect(await screen.findByText("نرمال‌سازی")).toBeInTheDocument();
  expect(screen.getAllByText("افتتاح حساب چطور است؟").length).toBeGreaterThan(0);
});

describe("failure semantics", () => {
  it("renders semantic fallback separately", () => {
    const trace = traceFixture({ fallback_used: true, fallback_reason: "NO_RETRIEVAL_RESULTS" });
    renderWithProviders(<TurnTrace turnId={trace.turn.id} initialTrace={trace} />);
    expect(screen.getByText("Semantic Fallback")).toBeInTheDocument();
    expect(screen.queryByText("Infrastructure Error")).not.toBeInTheDocument();
  });

  it("renders infrastructure failure separately", () => {
    const trace = traceFixture({ status: "ERROR", infrastructure_error: true, error_code: "VLLM_UNAVAILABLE" });
    renderWithProviders(<TurnTrace turnId={trace.turn.id} initialTrace={trace} />);
    expect(screen.getAllByText("Infrastructure Error").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("VLLM_UNAVAILABLE")).toBeInTheDocument();
    expect(screen.queryByText("Semantic Fallback")).not.toBeInTheDocument();
  });
});
