import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { App } from "../app/App";
import { DatasetImport } from "../components/dataset-import/DatasetImport";
import { renderWithProviders, jsonResponse } from "./helpers";
import type { ImportResponse } from "../types/api";

beforeEach(() => { vi.restoreAllMocks(); window.history.replaceState({}, "", "/"); });

describe("database setup gate", () => {
  it("requires the fixed confirmation and unlocks after initialization", async () => {
    let ready = false;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/login") && init?.method === "POST") return jsonResponse({ success: true, id: 1, username: "operator" });
      if (url.endsWith("/system/database-status")) return jsonResponse(ready ? { status: "READY", current_revision: "head", required_revision: "head", missing_objects: [], allow_initialize: true, error_code: null } : { status: "NOT_INITIALIZED", current_revision: null, required_revision: "head", missing_objects: ["table:datasets"], allow_initialize: true, error_code: null });
      if (url.endsWith("/system/database-initialize") && init?.method === "POST") { ready = true; return jsonResponse({ status: "READY", current_revision: "head", required_revision: "head", missing_objects: [], allow_initialize: true, error_code: null }); }
      if (url.endsWith("/runs")) return jsonResponse([]);
      if (url.endsWith("/system/capabilities")) return jsonResponse({ file_types: [".csv", ".xlsx"], max_upload_bytes: 10000, max_dataset_rows: 100, session_concurrency: 1, stability_default_concurrency: 1, allow_database_initialize: true });
      return jsonResponse([]);
    }));
    renderWithProviders(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("نام کاربری"), "operator");
    await user.type(screen.getByLabelText("رمز عبور"), "secret-password");
    await user.click(screen.getByRole("button", { name: "ورود با حساب RagBot" }));
    expect(await screen.findByText("پایگاه داده ارزیابی راه‌اندازی نشده است")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "ایجاد جداول ارزیابی" }));
    const dialog = screen.getByRole("dialog");
    const confirmInput = dialog.querySelector("input")!;
    expect(screen.getByRole("button", { name: "ایجاد جداول" })).toBeDisabled();
    await user.type(confirmInput, "CREATE_EVALUATION_TABLES");
    await user.click(screen.getByRole("button", { name: "ایجاد جداول" }));
    expect(await screen.findByText("بازپخش دقیق نشست‌ها")).toBeInTheDocument();
  });

  it("shows a recoverable API failure state", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/api/login")) return jsonResponse({ success: true, id: 1 });
      throw new Error("network unavailable");
    }));
    renderWithProviders(<App />); const user = userEvent.setup();
    await user.type(screen.getByLabelText("نام کاربری"), "operator");
    await user.type(screen.getByLabelText("رمز عبور"), "password");
    await user.click(screen.getByRole("button", { name: "ورود با حساب RagBot" }));
    expect(await screen.findByText("وضعیت پایگاه داده قابل دریافت نیست")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تلاش دوباره" })).toBeInTheDocument();
  });
});

it("renders dataset validation summary and parser warnings", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/system/capabilities")) return jsonResponse({ file_types: [".csv", ".xlsx"], max_upload_bytes: 10000, max_dataset_rows: 100, session_concurrency: 1, stability_default_concurrency: 1, allow_database_initialize: true });
    if (url.endsWith("/datasets/import")) return jsonResponse({ dataset: { id: "dataset-1", filename: "sample.csv", source_type: "FILE", file_sha256: "a".repeat(64), dataset_type: "PIPELINE_INSPECTION", row_count: 3, session_count: 2, valid_row_count: 2, invalid_row_count: 1, created_at: "2026-01-01T00:00:00Z", metadata: {} }, summary: { filename: "sample.csv", file_sha256: "a".repeat(64), row_count: 3, valid_row_count: 2, invalid_row_count: 1, session_count: 2, issues: [{ severity: "WARNING", code: "INVALID_TIMESTAMP", message: "زمان قابل تحلیل نیست", source_row_number: 3, field_name: "time" }] } });
    if (url.endsWith("/datasets/dataset-1/sessions")) return jsonResponse([{ id: "s1", turn_count: 2 }, { id: "s2", turn_count: 1 }]);
    return jsonResponse([]);
  }));
  function Harness() {
    const [value, setValue] = useState<ImportResponse | null>(null);
    return <DatasetImport datasetType="PIPELINE_INSPECTION" imported={value} onImported={setValue} />;
  }
  renderWithProviders(<Harness />);
  const user = userEvent.setup(); const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, new File(["query\nسلام"], "sample.csv", { type: "text/csv" }));
  await user.click(screen.getByRole("button", { name: "بارگذاری و تحلیل" }));
  expect(await screen.findByText("INVALID_TIMESTAMP")).toBeInTheDocument();
  expect(screen.getByText("زمان قابل تحلیل نیست")).toBeInTheDocument();
  await waitFor(() => expect(screen.getAllByText("2", { selector: ".metric-strip dd" }).length).toBeGreaterThanOrEqual(2));
});
