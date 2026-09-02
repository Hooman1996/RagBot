import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { parseSseBlock, streamSse } from "../api/sse";
import { ConversationBuilder } from "../features/stability-inspector/ConversationBuilder";
import { StabilityInspector } from "../features/stability-inspector/StabilityInspector";
import { StabilityResults } from "../features/stability-inspector/StabilityResults";
import { useRunEvents } from "../hooks/useRunEvents";
import { RunProgress } from "../components/runs/RunProgress";
import { renderWithProviders, jsonResponse, runSessionFixture, traceFixture } from "./helpers";

it("adds, reorders, and removes user-only conversation turns", async () => {
  const onChange = vi.fn(); const user = userEvent.setup();
  const { rerender } = renderWithProviders(<ConversationBuilder queries={["سؤال اول", "سؤال دوم"]} onChange={onChange} />);
  await user.click(screen.getByRole("button", { name: "افزودن پرسش پیگیرانه" }));
  expect(onChange).toHaveBeenLastCalledWith(["سؤال اول", "سؤال دوم", ""]);
  await user.click(screen.getAllByRole("button", { name: "انتقال به بالا" })[1]);
  expect(onChange).toHaveBeenLastCalledWith(["سؤال دوم", "سؤال اول"]);
  rerender(<ConversationBuilder queries={["سؤال اول", "سؤال دوم"]} onChange={onChange} />);
  await user.click(screen.getAllByRole("button", { name: "حذف نوبت" })[0]);
  expect(onChange).toHaveBeenLastCalledWith(["سؤال دوم"]);
});

it("validates repeat count before starting stability", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/runs")) return jsonResponse([]);
    if (url.endsWith("/datasources")) return jsonResponse([{ title: "General_FAQ" }]);
    if (url.endsWith("/system/capabilities")) return jsonResponse({ file_types: [".csv", ".xlsx"], max_upload_bytes: 10000, max_dataset_rows: 100, session_concurrency: 1, stability_default_concurrency: 1, allow_database_initialize: true });
    return jsonResponse([]);
  }));
  renderWithProviders(<StabilityInspector activeRunId={null} onRunOpen={() => undefined} />); const user = userEvent.setup();
  const repeat = screen.getByRole("spinbutton"); await user.clear(repeat); await user.type(repeat, "1");
  expect(screen.getByText("عدد صحیح بین ۲ و ۱۰۰ وارد کنید.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "شروع آزمون پایداری" })).toBeDisabled();
});

it("uses backend first divergence as the canonical stability marker", async () => {
  const one = { ...runSessionFixture, id: "s1", repeat_index: 1, first_divergent_turn: 1, first_divergent_stage: "REWRITE" as const, metadata: { stability: { first_divergent_turn: 1, first_divergent_stage: "REWRITE" as const, fallback_count: 0, fallback_rate: 0, incomparable_turn_count: 0, unique_variants: {}, variant_counts: { answer: 2 } } } };
  const two = { ...one, id: "s2", repeat_index: 2 };
  const traceA = traceFixture({}, "a"); const traceB = traceFixture({ rewritten_query: "بازنویسی متفاوت" }, "b");
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/runs/run-1")) return jsonResponse({ id: "run-1", status: "COMPLETED", run_type: "STABILITY_QUERY", config_snapshot: {}, total_sessions: 2, completed_sessions: 2, total_turns: 2, completed_turns: 2, fallback_count: 0, error_count: 0, infrastructure_error_count: 0, created_at: "2026-01-01", started_at: null, finished_at: null, cancel_requested_at: null, heartbeat_at: null, failure_code: null, metadata: {} });
    if (url.endsWith("/runs/run-1/sessions")) return jsonResponse([one, two]);
    if (url.endsWith("/run-sessions/s1")) return jsonResponse({ id: "s1", status: "COMPLETED", repeat_index: 1, turns: [{ id: "turn-a", turn_index: 1 }] });
    if (url.endsWith("/run-sessions/s2")) return jsonResponse({ id: "s2", status: "COMPLETED", repeat_index: 2, turns: [{ id: "turn-b", turn_index: 1 }] });
    if (url.endsWith("/run-turns/turn-a/trace")) return jsonResponse(traceA);
    if (url.endsWith("/run-turns/turn-b/trace")) return jsonResponse(traceB);
    return jsonResponse([]);
  }));
  renderWithProviders(<StabilityResults runId="run-1" />); const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /458923/ }));
  expect(await screen.findByText("مقایسه دو تکرار")).toBeInTheDocument();
  expect(screen.getAllByText("اولین واگرایی").length).toBeGreaterThan(0);
  expect(screen.getAllByText("DIVERGED").length).toBeGreaterThan(0);
});

describe("SSE client", () => {
  it("parses named events and IDs", () => {
    expect(parseSseBlock('id: 42\nevent: progress\ndata: {"completed_turns":2}')).toEqual({ id: "42", event: "progress", data: { completed_turns: 2 } });
  });
  it("classifies the backend Redis outage comment", () => {
    expect(parseSseBlock(": redis unavailable; durable state remains in PostgreSQL")).toEqual({ event: "redis_unavailable", data: { error_code: "EVALUATION_REDIS_UNAVAILABLE" } });
  });
  it("streams progress updates from a fetch body", async () => {
    const events: string[] = [];
    const response = new Response('event: progress\ndata: {"completed_turns":1}\n\nevent: run_completed\ndata: {"status":"COMPLETED"}\n\n');
    await streamSse(response, (event) => events.push(event.event));
    expect(events).toEqual(["progress", "run_completed"]);
  });
  it("surfaces live progress updates to the UI hook", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response('event: progress\ndata: {"completed_turns":4}\n\nevent: run_completed\ndata: {"status":"COMPLETED"}\n\n', { headers: { "Content-Type": "text/event-stream" } })));
    function Probe() {
      const { lastEvent } = useRunEvents("run-live", true);
      return <output>{lastEvent ? `${lastEvent.event}:${String(lastEvent.data.completed_turns ?? lastEvent.data.status)}` : "waiting"}</output>;
    }
    renderWithProviders(<Probe />);
    expect(await screen.findByText("run_completed:COMPLETED")).toBeInTheDocument();
  });
});

it("renders a failed run as an explicit terminal failure", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    if (String(input).endsWith("/runs/run-failed")) return jsonResponse({
      id: "run-failed", status: "FAILED", run_type: "DATASET_INSPECTION", dataset_id: "dataset-1",
      config_snapshot: {}, total_sessions: 2, completed_sessions: 1, total_turns: 3, completed_turns: 1,
      fallback_count: 0, error_count: 1, infrastructure_error_count: 1, git_commit_sha: null,
      created_at: "2026-01-01", started_at: "2026-01-01", finished_at: "2026-01-01",
      cancel_requested_at: null, heartbeat_at: null, failure_code: "CUDA_WORKER_INIT_FAILED", metadata: {},
    });
    return jsonResponse([]);
  }));
  renderWithProviders(<RunProgress runId="run-failed" />);
  expect((await screen.findAllByText("Failed")).length).toBeGreaterThan(0);
  expect(screen.getByText("CUDA_WORKER_INIT_FAILED")).toBeInTheDocument();
});
