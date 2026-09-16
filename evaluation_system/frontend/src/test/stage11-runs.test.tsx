import { QueryClient } from "@tanstack/react-query";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { App } from "../app/App";
import { TurnTrace } from "../components/trace/TurnTrace";
import { useRunEvents } from "../hooks/useRunEvents";
import { jsonResponse, renderWithProviders, runSessionFixture, traceFixture } from "./helpers";

const run = {
  id: "run-stage-11", dataset_id: "dataset-1", run_type: "DATASET_INSPECTION", status: "COMPLETED",
  config_snapshot: {}, total_sessions: 2, completed_sessions: 2, total_turns: 3, completed_turns: 3,
  fallback_count: 1, error_count: 0, infrastructure_error_count: 0, git_commit_sha: "abc123def456",
  created_at: "2026-09-16T10:00:00Z", started_at: "2026-09-16T10:00:01Z", finished_at: "2026-09-16T10:00:05Z",
  cancel_requested_at: null, heartbeat_at: null, failure_code: null, metadata: {},
};
const dataset = { id: "dataset-1", filename: "production-eval.csv", source_type: "FILE", file_sha256: "a".repeat(64), dataset_type: "PIPELINE_INSPECTION", row_count: 3, session_count: 2, valid_row_count: 3, invalid_row_count: 0, created_at: "2026-09-16T09:00:00Z", metadata: {} };

beforeEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/?panel=runs");
});

it("renders real runs and opens the unified Run Inspector", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/system/database-status")) return jsonResponse({ status: "READY", current_revision: "head", required_revision: "head", missing_objects: [], allow_initialize: false, error_code: null });
    if (url.endsWith("/runs/run-stage-11/sessions")) return jsonResponse([]);
    if (url.endsWith("/runs/run-stage-11")) return jsonResponse(run);
    if (url.endsWith("/runs")) return jsonResponse([run]);
    if (url.endsWith("/datasets/dataset-1")) return jsonResponse(dataset);
    if (url.endsWith("/datasets")) return jsonResponse([dataset]);
    return jsonResponse([]);
  }));
  renderWithProviders(<App />);
  expect(await screen.findByRole("heading", { name: "اجراها" })).toBeInTheDocument();
  expect((await screen.findAllByText("production-eval.csv")).length).toBeGreaterThan(0);
  await userEvent.click(screen.getByRole("button", { name: "run-stage-11" }));
  expect(await screen.findByText("بازگشت به اجراها")).toBeInTheDocument();
  expect(window.location.search).toBe("?panel=runs&run=run-stage-11");
});

it("loads only the selected session and selected turn trace", async () => {
  window.history.replaceState({}, "", "/?panel=runs&run=run-stage-11");
  const second = { ...runSessionFixture, id: "run-session-2", source_session_id: "session-two", repeat_index: 2, first_query: "پرسش دوم" };
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/system/database-status")) return jsonResponse({ status: "READY", current_revision: "head", required_revision: "head", missing_objects: [], allow_initialize: false, error_code: null });
    if (url.endsWith("/runs/run-stage-11/sessions")) return jsonResponse([runSessionFixture, second]);
    if (url.endsWith("/runs/run-stage-11")) return jsonResponse(run);
    if (url.endsWith("/datasets/dataset-1")) return jsonResponse(dataset);
    if (url.endsWith("/run-sessions/run-session-1")) return jsonResponse({ id: "run-session-1", status: "COMPLETED", repeat_index: 1, turns: [{ ...traceFixture().turn, id: "turn-a" }] });
    if (url.endsWith("/run-sessions/run-session-2")) return jsonResponse({ id: "run-session-2", status: "COMPLETED", repeat_index: 2, turns: [{ ...traceFixture({}, "b").turn, id: "turn-b" }, { ...traceFixture({}, "c").turn, id: "turn-c", turn_index: 2, raw_query: "نوبت دوم انتخابی" }] });
    if (url.endsWith("/run-turns/turn-a/trace")) return jsonResponse(traceFixture());
    if (url.endsWith("/run-turns/turn-b/trace")) return jsonResponse(traceFixture({}, "b"));
    if (url.endsWith("/run-turns/turn-c/trace")) return jsonResponse(traceFixture({}, "c"));
    if (url.endsWith("/datasets")) return jsonResponse([dataset]);
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  renderWithProviders(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /session-two/ }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/run-sessions/run-session-2"), expect.anything()));
  await userEvent.click(await screen.findByRole("button", { name: /نوبت دوم انتخابی/ }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/run-turns/turn-c/trace"), expect.anything()));
});

it("selects all nine stages and renders real retrieval and rerank payloads", async () => {
  const trace = traceFixture();
  renderWithProviders(<TurnTrace turnId={trace.turn.id} initialTrace={trace} />);
  const labels = ["نرمال‌سازی", "تاریخچه", "بازنویسی", "نیت", "بازیابی", "بازرتبه‌بندی", "زمینه", "پرامپت", "تولید"];
  for (const label of labels) {
    const tab = screen.getByRole("tab", { name: new RegExp(label) });
    await userEvent.click(tab);
    expect(tab).toHaveAttribute("aria-selected", "true");
  }
  await userEvent.click(screen.getByRole("tab", { name: /بازیابی/ }));
  expect(screen.getByText("نتایج بازیابی پیش از Rerank")).toBeInTheDocument();
  expect(screen.getByText("محتوای بانکی")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: /بازرتبه‌بندی/ }));
  expect(screen.getByText(/#8 → #1/)).toBeInTheDocument();
});

it("invalidates targeted query keys for PostgreSQL-backed SSE events", async () => {
  const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
  vi.stubGlobal("fetch", vi.fn(async () => new Response([
    'event: progress\ndata: {"completed_turns":1}',
    'event: turn_completed\ndata: {"run_session_id":"session-1","run_turn_id":"turn-1"}',
    'event: stage_completed\ndata: {"run_session_id":"session-1","run_turn_id":"turn-1","stage_name":"RETRIEVAL"}',
    'event: run_completed\ndata: {"status":"COMPLETED"}',
  ].join("\n\n") + "\n\n")));
  function Probe() { useRunEvents("run-live", true); return null; }
  renderWithProviders(<Probe />);
  await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["turn-trace", "turn-1"] }));
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["run", "run-live"] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["run-sessions", "run-live"] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["run-session", "session-1"] });
});
