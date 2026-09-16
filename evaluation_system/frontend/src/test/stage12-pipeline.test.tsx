import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../app/App";
import { jsonResponse, runSessionFixture, traceFixture, renderWithProviders } from "./helpers";

const run = {
  id: "run-pipeline-12", dataset_id: "dataset-12", run_type: "DATASET_INSPECTION", status: "COMPLETED",
  config_snapshot: {}, total_sessions: 2, completed_sessions: 2, total_turns: 3, completed_turns: 3,
  fallback_count: 1, error_count: 0, infrastructure_error_count: 0, git_commit_sha: "deadbeef12345678",
  created_at: "2026-09-16T10:00:00Z", started_at: "2026-09-16T10:00:01Z", finished_at: "2026-09-16T10:00:05Z",
  cancel_requested_at: null, heartbeat_at: null, failure_code: null, metadata: {},
};
const secondSession = { ...runSessionFixture, id: "session-pipeline-2", run_id: run.id, source_session_id: "source-session-2", repeat_index: 2, turn_count: 2 };
const sessions = [{ ...runSessionFixture, id: "session-pipeline-1", run_id: run.id }, secondSession];

function installApi(trace = traceFixture()) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/system/database-status")) return jsonResponse({ status: "READY", current_revision: "head", required_revision: "head", missing_objects: [], allow_initialize: false, error_code: null });
    if (url.endsWith(`/runs/${run.id}/sessions`)) return jsonResponse(sessions);
    if (url.endsWith(`/runs/${run.id}`)) return jsonResponse(run);
    if (url.endsWith("/runs")) return jsonResponse([run]);
    if (url.endsWith("/run-sessions/session-pipeline-1")) return jsonResponse({ id: "session-pipeline-1", status: "COMPLETED", repeat_index: 1, turns: [{ ...trace.turn, id: "turn-pipeline-1" }] });
    if (url.endsWith("/run-sessions/session-pipeline-2")) return jsonResponse({ id: "session-pipeline-2", status: "COMPLETED", repeat_index: 2, turns: [{ ...trace.turn, id: "turn-pipeline-2", raw_query: "پرسش نوبت دوم" }, { ...trace.turn, id: "turn-pipeline-3", turn_index: 2, raw_query: "پرسش نوبت سوم" }] });
    if (url.includes("/run-turns/") && url.endsWith("/trace")) return jsonResponse(trace);
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/?panel=pipeline");
});

describe("Stage 12 Pipeline Explorer", () => {
  it("enables Pipeline in the sidebar and lists runs from the real runs API without global-search controls", async () => {
    const fetchMock = installApi();
    renderWithProviders(<App />);
    expect(await screen.findByRole("button", { name: "خط لوله" })).toBeEnabled();
    expect(await screen.findByRole("button", { name: `انتخاب اجرای ${run.id}` })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/runs$/), expect.anything());
    expect(screen.getByLabelText("فیلتر Run ID")).toBeInTheDocument();
    expect(screen.queryByLabelText(/جست‌وجوی سراسری|global hash|global intent/i)).not.toBeInTheDocument();
  });

  it("progressively loads the selected run, session, turn and shared specialized inspector", async () => {
    const fetchMock = installApi();
    renderWithProviders(<App />);
    await userEvent.click(await screen.findByRole("button", { name: `انتخاب اجرای ${run.id}` }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining(`/runs/${run.id}/sessions`), expect.anything()));
    await userEvent.click(await screen.findByRole("button", { name: /انتخاب جلسه source-session-2/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/run-sessions/session-pipeline-2"), expect.anything()));
    await userEvent.click(await screen.findByRole("button", { name: /انتخاب نوبت 2: پرسش نوبت سوم/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/run-turns/turn-pipeline-3/trace"), expect.anything()));
    await userEvent.click(await screen.findByRole("tab", { name: /بازیابی/ }));
    expect(await screen.findByText("نتایج بازیابی پیش از Rerank")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rerank" })).toBeInTheDocument();
    expect(window.location.search).toContain("stage=RETRIEVAL");
  });

  it("restores the complete deep link and keeps all nine stages selectable", async () => {
    window.history.replaceState({}, "", `/?panel=pipeline&run=${run.id}&session=session-pipeline-2&turn=turn-pipeline-3&stage=PROMPT_BUILD`);
    installApi();
    renderWithProviders(<App />);
    expect(await screen.findByText("پیام‌های پرامپت")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /پرامپت/ })).toHaveAttribute("aria-selected", "true");
    const labels = ["نرمال‌سازی", "تاریخچه", "بازنویسی", "نیت", "بازیابی", "بازرتبه‌بندی", "زمینه", "پرامپت", "تولید"];
    for (const label of labels) {
      const tab = screen.getByRole("tab", { name: new RegExp(label) });
      await userEvent.click(tab);
      expect(tab).toHaveAttribute("aria-selected", "true");
    }
    expect(window.location.search).toContain("run=run-pipeline-12");
    expect(window.location.search).toContain("session=session-pipeline-2");
    expect(window.location.search).toContain("turn=turn-pipeline-3");
  });

  it("renders an older trace without HISTORY safely", async () => {
    const oldTrace = traceFixture();
    oldTrace.stages = oldTrace.stages.filter((item) => item.stage_name !== "HISTORY").map((item) => item.stage_name === "REWRITE" ? { ...item, input_data: {} } : item);
    window.history.replaceState({}, "", `/?panel=pipeline&run=${run.id}&session=session-pipeline-1&turn=turn-pipeline-1&stage=HISTORY`);
    installApi(oldTrace);
    renderWithProviders(<App />);
    expect(await screen.findByText("این مرحله در این trace موجود نیست.")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /تاریخچه/ })).toHaveAttribute("aria-selected", "true");
  });
});
