import type {
  Capabilities, DatabaseStatus, Dataset, DatasetSession, DatasetTurn, Datasource,
  IdResponse, ImportResponse, Run, RunSession, RunSessionDetail, TurnTrace,
} from "../types/api";

const configuredBase = (import.meta.env.VITE_EVALUATION_API_BASE || "/api/v1/evaluation").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let body: unknown;
  try { body = await response.json(); } catch { body = null; }
  const record = body && typeof body === "object" ? body as Record<string, unknown> : {};
  const detail = record.detail && typeof record.detail === "object" ? record.detail as Record<string, unknown> : record;
  const code = String(detail.error_code || `HTTP_${response.status}`);
  const message = String(detail.message || code);
  return new ApiError(response.status, code, message, detail);
}

export class EvaluationApiClient {
  get baseUrl(): string { return configuredBase; }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
    const response = await fetch(`${configuredBase}${path}`, {
      ...init, headers, cache: "no-store", credentials: "same-origin",
    });
    if (!response.ok) throw await parseError(response);
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  async login(username: string, password: string): Promise<void> {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) throw await parseError(response);
  }

  databaseStatus = () => this.request<DatabaseStatus>("/system/database-status");
  initializeDatabase = () => this.request<DatabaseStatus>("/system/database-initialize", {
    method: "POST", body: JSON.stringify({ confirmation: "CREATE_EVALUATION_TABLES" }),
  });
  capabilities = () => this.request<Capabilities>("/system/capabilities");
  datasources = () => this.request<Datasource[]>("/datasources");

  importDataset(file: File, datasetType: "PIPELINE_INSPECTION" | "STABILITY") {
    const form = new FormData();
    form.append("file", file);
    form.append("dataset_type", datasetType);
    return this.request<ImportResponse>("/datasets/import", { method: "POST", body: form });
  }
  datasets = () => this.request<Dataset[]>("/datasets");
  dataset = (id: string) => this.request<Dataset>(`/datasets/${id}`);
  datasetSessions = (id: string) => this.request<DatasetSession[]>(`/datasets/${id}/sessions`);
  datasetTurns = (id: string) => this.request<DatasetTurn[]>(`/datasets/sessions/${id}/turns`);
  deleteDataset = (id: string) => this.request<{ deleted: boolean }>(`/datasets/${id}`, { method: "DELETE" });

  createRun(body: { dataset_id: string; run_type: Run["run_type"]; repeat_count: number; documents: string[] }) {
    return this.request<IdResponse>("/runs", { method: "POST", body: JSON.stringify(body) });
  }
  manualStability(body: { queries: string[]; repeat_count: number; documents: string[] }) {
    return this.request<IdResponse>("/stability/manual", { method: "POST", body: JSON.stringify(body) });
  }
  runs = () => this.request<Run[]>("/runs");
  run = (id: string) => this.request<Run>(`/runs/${id}`);
  runSessions = (id: string) => this.request<RunSession[]>(`/runs/${id}/sessions`);
  runSession = (id: string) => this.request<RunSessionDetail>(`/run-sessions/${id}`);
  turnTrace = (id: string) => this.request<TurnTrace>(`/run-turns/${id}/trace`);
  cancelRun = (id: string) => this.request<{ id: string; status: string }>(`/runs/${id}/cancel`, { method: "POST" });
  deleteRun = (id: string) => this.request<{ deleted: boolean }>(`/runs/${id}`, { method: "DELETE" });

  async eventResponse(runId: string, signal: AbortSignal, lastEventId?: string): Promise<Response> {
    const headers = new Headers({ Accept: "text/event-stream" });
    if (lastEventId) headers.set("Last-Event-ID", lastEventId);
    const response = await fetch(`${configuredBase}/runs/${runId}/events`, {
      headers, signal, cache: "no-store", credentials: "same-origin",
    });
    if (!response.ok) throw await parseError(response);
    return response;
  }
}
