import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../app/App";
import { StabilityInspector } from "../features/stability-inspector/StabilityInspector";
import { StabilityResults } from "../features/stability-inspector/StabilityResults";
import { matrixState, type LoadedAttempt } from "../features/stability-inspector/stabilityModel";
import type { RunSession } from "../types/api";
import { jsonResponse, renderWithProviders, runSessionFixture, traceFixture } from "./helpers";

const capabilities = { file_types: [".csv", ".xlsx"], max_upload_bytes: 10000, max_dataset_rows: 100, session_concurrency: 2, stability_default_concurrency: 1, repeat_max: 10, background_execution_available: true, allow_database_initialize: false };
const database = { status: "READY", current_revision: "20260901", required_revision: "20260901", missing_objects: [], allow_initialize: false, error_code: null };
const run = { id: "run-stability", dataset_id: null, run_type: "STABILITY_QUERY", status: "COMPLETED", config_snapshot: {}, total_sessions: 2, completed_sessions: 2, total_turns: 2, completed_turns: 2, fallback_count: 0, error_count: 0, infrastructure_error_count: 0, git_commit_sha: null, created_at: "2026-09-16T10:00:00Z", started_at: null, finished_at: null, cancel_requested_at: null, heartbeat_at: null, failure_code: null, metadata: {} };

beforeEach(() => { vi.restoreAllMocks(); window.history.replaceState({}, "", "/"); });

function setupFetch(onRequest?: (url: string, init?: RequestInit) => Response | undefined) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); const custom = onRequest?.(url, init); if (custom) return custom;
    if (url.endsWith("/system/database-status")) return jsonResponse(database);
    if (url.endsWith("/system/capabilities")) return jsonResponse(capabilities);
    if (url.endsWith("/datasources")) return jsonResponse([{ title: "General_FAQ" }]);
    if (url.endsWith("/datasets")) return jsonResponse([]);
    if (url.endsWith("/runs")) return jsonResponse([]);
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock); return fetchMock;
}

describe("stability creation", () => {
  it("creates single-query and conversation stability with independent ordered queries", async () => {
    const bodies: unknown[] = []; setupFetch((url, init) => {
      if (url.endsWith("/stability/manual") && init?.method === "POST") { bodies.push(JSON.parse(String(init.body))); return jsonResponse({ id: `new-${bodies.length}`, status: "PENDING" }); }
    });
    const open = vi.fn(); const user = userEvent.setup();
    const view = renderWithProviders(<StabilityInspector activeRunId={null} onRunOpen={open} />);
    await user.type(await screen.findByPlaceholderText("پرسش مورد بررسی را وارد کنید"), "پرسش تکی");
    await user.click(screen.getByRole("checkbox", { name: "General_FAQ" }));
    await user.click(screen.getByRole("button", { name: "شروع آزمون پایداری" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith("new-1"));
    expect(bodies[0]).toMatchObject({ queries: ["پرسش تکی"], repeat_count: 3, documents: ["General_FAQ"] });
    view.unmount();

    renderWithProviders(<StabilityInspector activeRunId={null} onRunOpen={open} />);
    await user.click(await screen.findByRole("tab", { name: /مکالمه/ }));
    const turns = screen.getAllByRole("textbox");
    await user.type(turns[0], "نوبت اول"); await user.type(turns[1], "نوبت دوم");
    await user.click(screen.getByRole("checkbox", { name: "General_FAQ" }));
    await user.click(screen.getByRole("button", { name: "شروع آزمون پایداری" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({ queries: ["نوبت اول", "نوبت دوم"], repeat_count: 3 });
  });

  it("reuses DatasetImport and creates STABILITY_DATASET", async () => {
    let runBody: Record<string, unknown> | null = null; setupFetch((url, init) => {
      if (url.endsWith("/datasets/import")) return jsonResponse({ dataset: { id: "dataset-stability", filename: "stability.csv", source_type: "FILE", file_sha256: "a".repeat(64), dataset_type: "STABILITY", row_count: 1, session_count: 1, valid_row_count: 1, invalid_row_count: 0, created_at: "2026-09-16", metadata: {} }, summary: { filename: "stability.csv", file_sha256: "a".repeat(64), row_count: 1, valid_row_count: 1, invalid_row_count: 0, session_count: 1, issues: [] } });
      if (url.endsWith("/runs") && init?.method === "POST") { runBody = JSON.parse(String(init.body)); return jsonResponse({ id: "dataset-run", status: "PENDING" }); }
    });
    const user = userEvent.setup(); const open = vi.fn(); renderWithProviders(<StabilityInspector activeRunId={null} onRunOpen={open} />);
    await user.click(await screen.findByRole("tab", { name: /مجموعه داده/ }));
    await user.upload(screen.getByLabelText("انتخاب فایل مجموعه داده"), new File(["query\nhello"], "stability.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "بارگذاری و تحلیل" }));
    expect(await screen.findByText("مجموعه داده وارد شد")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "General_FAQ" }));
    await user.click(screen.getByRole("button", { name: "شروع آزمون پایداری" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith("dataset-run"));
    expect(runBody).toMatchObject({ dataset_id: "dataset-stability", run_type: "STABILITY_DATASET", repeat_count: 3 });
  });
});

describe("stability analysis", () => {
  it("classifies matrix cells from real trace data without treating missing data as divergence", () => {
    const session = runSessionFixture; const turn = traceFixture({}, "same").turn;
    const baseline: LoadedAttempt = { session, turn, trace: traceFixture({}, "same"), traceError: null };
    expect(matrixState(baseline, baseline, true)).toBe("baseline");
    expect(matrixState({ ...baseline, session: { ...session, repeat_index: 2 } }, baseline, false)).toBe("same");
    expect(matrixState({ ...baseline, session: { ...session, repeat_index: 2 }, trace: traceFixture({ actual_answer: "متفاوت" }, "same") }, baseline, false)).toBe("different");
    expect(matrixState(undefined, baseline, false)).toBe("unavailable");
    expect(matrixState({ ...baseline, trace: null, traceError: new Error("failed") }, baseline, false)).toBe("error");
  });

  it("groups by canonical key and fetches traces only for the selected group", async () => {
    const first: RunSession = { ...runSessionFixture, id: "group-a-1", dataset_session_id: "logical-a", source_session_id: "A", repeat_index: 1 };
    const first2 = { ...first, id: "group-a-2", repeat_index: 2 };
    const second: RunSession = { ...runSessionFixture, id: "group-b-1", dataset_session_id: "logical-b", source_session_id: "B", repeat_index: 1 };
    const second2 = { ...second, id: "group-b-2", repeat_index: 2 };
    const calls: string[] = []; setupFetch((url) => {
      calls.push(url);
      if (url.endsWith("/runs/run-stability")) return jsonResponse(run);
      if (url.endsWith("/runs/run-stability/sessions")) return jsonResponse([first, first2, second, second2]);
      const detail = [first, first2, second, second2].find((item) => url.endsWith(`/run-sessions/${item.id}`));
      if (detail) return jsonResponse({ id: detail.id, status: "COMPLETED", repeat_index: detail.repeat_index, turns: [{ ...traceFixture({}, detail.id).turn, id: `turn-${detail.id}` }] });
      if (url.includes("/run-turns/turn-group-a")) return jsonResponse(traceFixture({}, url.includes("a-1") ? "a1" : "a2"));
      if (url.includes("/run-turns/turn-group-b")) return jsonResponse(traceFixture({}, url.includes("b-1") ? "b1" : "b2"));
    });
    const user = userEvent.setup(); renderWithProviders(<StabilityResults runId="run-stability" />);
    expect(await screen.findByRole("heading", { name: "مقایسه A/B نوبت 1" })).toBeInTheDocument();
    expect(screen.getAllByText(/پاسخ/).length).toBeGreaterThan(0);
    expect(calls.some((url) => url.includes("run-sessions/group-a"))).toBe(true);
    expect(calls.some((url) => url.includes("run-sessions/group-b"))).toBe(false);
    await user.click(screen.getByRole("button", { name: /^B/ }));
    await waitFor(() => expect(calls.some((url) => url.includes("run-sessions/group-b"))).toBe(true));
  });
});

describe("system and navigation", () => {
  it("renders honest database, capability, datasource, and run evidence", async () => {
    setupFetch((url) => url.endsWith("/runs") ? jsonResponse([{ ...run, id: "pending", status: "PENDING", heartbeat_at: null }, { ...run, id: "active", status: "RUNNING", heartbeat_at: "2026-09-16T10:00:00Z" }, { ...run, id: "failed", status: "FAILED" }]) : undefined);
    window.history.replaceState({}, "", "/?panel=system"); renderWithProviders(<App />);
    expect(await screen.findByRole("heading", { name: "سیستم و عملیات" })).toBeInTheDocument();
    expect(await screen.findByText("RagBot datasource endpoint reachable")).toBeInTheDocument();
    expect(screen.getByText("قابلیت اجرای پس‌زمینه")).toBeInTheDocument();
    expect(screen.queryByText(/Worker Healthy/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/RagBot health/i)).not.toBeInTheDocument();
    expect(screen.getByText("Pending runs").nextSibling).toHaveTextContent("۱");
    expect(screen.getByText("Active runs").nextSibling).toHaveTextContent("۱");
  });

  it("enables all six destinations and clears deep-link state on top-level navigation", async () => {
    setupFetch(); window.history.replaceState({}, "", "/?panel=pipeline&run=r&session=s&turn=t&stage=GENERATION"); renderWithProviders(<App />); const user = userEvent.setup();
    const names = ["نمای کلی", "مجموعه داده‌ها", "اجراها", "پایداری", "خط لوله", "سیستم"];
    await screen.findByRole("button", { name: "نمای کلی" });
    for (const name of names) expect(screen.getByRole("button", { name })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "سیستم" }));
    expect(await screen.findByRole("heading", { name: "سیستم و عملیات" })).toBeInTheDocument();
    expect(window.location.search).toBe("?panel=system");
  });
});
