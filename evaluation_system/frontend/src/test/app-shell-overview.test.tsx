import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { App } from "../app/App";
import { jsonResponse, renderWithProviders } from "./helpers";

const runs = [
  {
    id: "run-recent-1", dataset_id: "dataset-1", run_type: "DATASET_INSPECTION", status: "COMPLETED",
    config_snapshot: {}, total_sessions: 2, completed_sessions: 2, total_turns: 6, completed_turns: 6,
    fallback_count: 1, error_count: 0, infrastructure_error_count: 0, git_commit_sha: "abc123",
    created_at: "2026-09-15T10:00:00Z", started_at: "2026-09-15T10:00:01Z", finished_at: "2026-09-15T10:01:00Z",
    cancel_requested_at: null, heartbeat_at: null, failure_code: null, metadata: {},
  },
  {
    id: "run-live-2", dataset_id: null, run_type: "STABILITY_QUERY", status: "RUNNING",
    config_snapshot: {}, total_sessions: 3, completed_sessions: 1, total_turns: 3, completed_turns: 1,
    fallback_count: 0, error_count: 0, infrastructure_error_count: 0, git_commit_sha: null,
    created_at: "2026-09-16T10:00:00Z", started_at: "2026-09-16T10:00:01Z", finished_at: null,
    cancel_requested_at: null, heartbeat_at: "2026-09-16T10:00:03Z", failure_code: null, metadata: {},
  },
];

beforeEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/system/database-status")) return jsonResponse({ status: "READY", current_revision: "head", required_revision: "head", missing_objects: [], allow_initialize: false, error_code: null });
    if (url.endsWith("/system/capabilities")) return jsonResponse({ file_types: [".csv", ".xlsx"], max_upload_bytes: 10000, max_dataset_rows: 100, session_concurrency: 1, stability_default_concurrency: 1, repeat_max: 10, background_execution_available: true, allow_database_initialize: false });
    if (url.endsWith("/datasources")) return jsonResponse([{ title: "General_FAQ" }]);
    if (url.endsWith("/datasets")) return jsonResponse([{ id: "dataset-1", filename: "eval.csv", source_type: "FILE", file_sha256: "a".repeat(64), dataset_type: "PIPELINE_INSPECTION", row_count: 6, session_count: 2, valid_row_count: 6, invalid_row_count: 0, created_at: "2026-09-15T09:00:00Z", metadata: {} }]);
    if (url.endsWith("/datasets/dataset-1")) return jsonResponse({ id: "dataset-1", filename: "eval.csv", source_type: "FILE", file_sha256: "a".repeat(64), dataset_type: "PIPELINE_INSPECTION", row_count: 6, session_count: 2, valid_row_count: 6, invalid_row_count: 0, created_at: "2026-09-15T09:00:00Z", metadata: {} });
    if (url.endsWith("/runs")) return jsonResponse(runs);
    return jsonResponse([]);
  }));
});

it("renders Overview by default without a login gate and uses current API response fields", async () => {
  renderWithProviders(<App />);
  expect(await screen.findByRole("heading", { name: "نمای کلی ارزیابی" })).toBeInTheDocument();
  expect(screen.queryByText("ورود به کنسول ارزیابی")).not.toBeInTheDocument();
  expect(await screen.findByTitle("run-live-2")).toBeInTheDocument();
  expect(screen.getByText("اجرای پس‌زمینه فعال")).toBeInTheDocument();
  expect(window.location.search).toBe("");
});

it("navigates between Overview, Datasets, and Stability and follows browser history state", async () => {
  renderWithProviders(<App />);
  const user = userEvent.setup();
  await screen.findByRole("heading", { name: "نمای کلی ارزیابی" });
  await user.click(screen.getByRole("button", { name: "مجموعه داده‌ها" }));
  expect(await screen.findByRole("heading", { name: "مجموعه داده‌ها" })).toBeInTheDocument();
  expect(window.location.search).toBe("?panel=datasets");
  await user.click(screen.getByRole("button", { name: "پایداری" }));
  expect(await screen.findByRole("heading", { name: "ردیابی نقطه نخست واگرایی" })).toBeInTheDocument();
  expect(window.location.search).toBe("?panel=stability");
  act(() => {
    window.history.replaceState({}, "", "/?panel=datasets");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  expect(await screen.findByRole("heading", { name: "مجموعه داده‌ها" })).toBeInTheDocument();
});
