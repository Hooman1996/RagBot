import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DatasetInspector } from "../features/dataset-inspector/DatasetInspector";
import type { Dataset, DatasetSession } from "../types/api";
import { jsonResponse, renderWithProviders } from "./helpers";

const datasetOne: Dataset = {
  id: "dataset-1", filename: "history.csv", source_type: "FILE", file_sha256: "a".repeat(64), dataset_type: "PIPELINE_INSPECTION",
  row_count: 4, session_count: 2, valid_row_count: 4, invalid_row_count: 0, created_at: "2026-09-15T09:00:00Z", metadata: {},
};
const datasetTwo: Dataset = {
  id: "dataset-2", filename: "stability.xlsx", source_type: "FILE", file_sha256: "b".repeat(64), dataset_type: "STABILITY",
  row_count: 2, session_count: 1, valid_row_count: 1, invalid_row_count: 1, created_at: "2026-09-14T09:00:00Z", metadata: {},
};
const sessions: DatasetSession[] = [
  { id: "session-1", source_session_id: "source-A", synthetic_session: false, first_source_row: 2, first_source_timestamp: "2026-01-01T10:00:00Z", last_source_timestamp: "2026-01-01T10:01:00Z", turn_count: 2, metadata: {} },
  { id: "session-2", source_session_id: null, synthetic_session: true, first_source_row: 4, first_source_timestamp: null, last_source_timestamp: null, turn_count: 1, metadata: {} },
];

function capabilities() {
  return { file_types: [".csv", ".xlsx"], max_upload_bytes: 10000, max_dataset_rows: 100, session_concurrency: 1, stability_default_concurrency: 1, repeat_max: 10, background_execution_available: true, allow_database_initialize: false };
}

function installApi(options: { datasets?: Dataset[]; onFetch?: (url: string, init?: RequestInit) => Response | undefined | Promise<Response | undefined> } = {}) {
  const listed = options.datasets ?? [datasetOne, datasetTwo];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const override = await options.onFetch?.(url, init);
    if (override) return override;
    if (url.endsWith("/system/capabilities")) return jsonResponse(capabilities());
    if (url.endsWith("/datasources")) return jsonResponse([{ title: "General_FAQ" }, { title: "Cards" }]);
    if (url.endsWith("/datasets")) return jsonResponse(listed);
    if (url.endsWith("/datasets/dataset-1")) return jsonResponse(datasetOne);
    if (url.endsWith("/datasets/dataset-2")) return jsonResponse(datasetTwo);
    if (url.endsWith("/datasets/dataset-1/sessions")) return jsonResponse(sessions);
    if (url.endsWith("/datasets/dataset-2/sessions")) return jsonResponse([]);
    if (url.endsWith("/datasets/sessions/session-1/turns")) return jsonResponse([{ id: "turn-1", turn_index: 1, source_row_number: 2, source_time_raw: "10:00", source_timestamp: "2026-01-01T10:00:00Z", query: "پرسش اول", metadata: {} }]);
    if (url.endsWith("/datasets/sessions/session-2/turns")) return jsonResponse([{ id: "turn-2", turn_index: 1, source_row_number: 4, source_time_raw: null, source_timestamp: null, query: "پرسش مستقل", metadata: {} }]);
    if (url.endsWith("/runs")) return init?.method === "POST" ? jsonResponse({ id: "run-new", status: "PENDING" }) : jsonResponse([]);
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => vi.restoreAllMocks());

describe("production dataset inspector", () => {
  it("renders the dataset library from api.datasets", async () => {
    installApi();
    renderWithProviders(<DatasetInspector activeRunId={null} onRunOpen={vi.fn()} />);
    expect(await screen.findByText("history.csv")).toBeInTheDocument();
    expect(screen.getByText("stability.xlsx")).toBeInTheDocument();
    expect(screen.getByText("بدون ردیف نامعتبر")).toBeInTheDocument();
  });

  it("fetches sessions when another dataset is selected", async () => {
    const fetchMock = installApi();
    renderWithProviders(<DatasetInspector activeRunId={null} onRunOpen={vi.fn()} />);
    const user = userEvent.setup();
    await user.click((await screen.findByText("stability.xlsx")).closest("button")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/datasets/dataset-2/sessions"), expect.anything()));
  });

  it("fetches and renders turns for a selected session", async () => {
    const fetchMock = installApi();
    renderWithProviders(<DatasetInspector activeRunId={null} onRunOpen={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /session-2/ }));
    expect(await screen.findByText("پرسش مستقل")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/datasets/sessions/session-2/turns"), expect.anything());
  });

  it("refreshes datasets and selects a successful import", async () => {
    const imported: Dataset = { ...datasetOne, id: "dataset-new", filename: "new.csv", created_at: "2026-09-16T10:00:00Z" };
    let importedReady = false;
    installApi({
      onFetch: (url) => {
        if (url.endsWith("/datasets/import")) { importedReady = true; return jsonResponse({ dataset: imported, summary: { filename: imported.filename, file_sha256: imported.file_sha256, row_count: 4, valid_row_count: 4, invalid_row_count: 0, session_count: 2, issues: [] } }); }
        if (url.endsWith("/datasets") && importedReady) return jsonResponse([imported, datasetOne]);
        if (url.endsWith("/datasets/dataset-new/sessions")) return jsonResponse([]);
      },
    });
    renderWithProviders(<DatasetInspector activeRunId={null} onRunOpen={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "افزودن مجموعه داده" }));
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, new File(["query\nسلام"], "new.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "بارگذاری و تحلیل" }));
    await user.click(await screen.findByRole("button", { name: "مشاهده مجموعه واردشده" }));
    const library = screen.getByRole("complementary", { name: "کتابخانه مجموعه داده" });
    const selected = (await within(library).findByText("new.csv")).closest("button")!;
    expect(selected).toHaveAttribute("aria-pressed", "true");
  });

  it("starts evaluation with the selected dataset and datasource documents", async () => {
    let requestBody: Record<string, unknown> | null = null;
    const onRunOpen = vi.fn();
    installApi({ onFetch: (url, init) => {
      if (url.endsWith("/runs") && init?.method === "POST") { requestBody = JSON.parse(String(init.body)); return jsonResponse({ id: "run-new", status: "PENDING" }); }
    } });
    renderWithProviders(<DatasetInspector activeRunId={null} onRunOpen={onRunOpen} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "شروع ارزیابی" }));
    const dialog = screen.getByRole("dialog", { name: "تنظیم اجرای ارزیابی" });
    await user.click(within(dialog).getByRole("checkbox", { name: "General_FAQ" }));
    await user.click(within(dialog).getByRole("button", { name: "شروع ارزیابی" }));
    await waitFor(() => expect(onRunOpen).toHaveBeenCalledWith("run-new"));
    expect(requestBody).toEqual({ dataset_id: "dataset-1", run_type: "DATASET_INSPECTION", repeat_count: 1, documents: ["General_FAQ"] });
  });

  it("renders a guided empty dataset state", async () => {
    installApi({ datasets: [] });
    renderWithProviders(<DatasetInspector activeRunId={null} onRunOpen={vi.fn()} />);
    expect(await screen.findByText("هنوز مجموعه داده‌ای وجود ندارد")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "افزودن مجموعه داده" })).toHaveLength(2);
  });
});
