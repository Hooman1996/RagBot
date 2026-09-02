export type JsonObject = Record<string, unknown>;
export type DatabaseState = "NOT_INITIALIZED" | "READY" | "UPGRADE_REQUIRED" | "ERROR";
export type RunStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
export type StageName =
  | "NORMALIZATION"
  | "INTENT"
  | "REWRITE"
  | "RETRIEVAL"
  | "RERANK"
  | "CONTEXT_SELECTION"
  | "PROMPT_BUILD"
  | "GENERATION";

export interface DatabaseStatus {
  status: DatabaseState;
  current_revision: string | null;
  required_revision: string | null;
  missing_objects: string[];
  allow_initialize: boolean;
  error_code: string | null;
}

export interface Capabilities {
  file_types: string[];
  max_upload_bytes: number;
  max_dataset_rows: number;
  session_concurrency: number;
  stability_default_concurrency: number;
  repeat_max: number;
  background_execution_available: boolean;
  allow_database_initialize: boolean;
}

export interface Datasource { title: string }

export interface ImportIssue {
  severity: "WARNING" | "ERROR";
  code: string;
  message: string;
  source_row_number: number | null;
  field_name: string | null;
}

export interface Dataset {
  id: string;
  filename: string | null;
  source_type: "FILE" | "MANUAL";
  file_sha256: string | null;
  dataset_type: "PIPELINE_INSPECTION" | "STABILITY";
  row_count: number;
  session_count: number;
  valid_row_count: number;
  invalid_row_count: number;
  created_at: string;
  metadata: JsonObject;
}

export interface ImportSummary {
  filename: string | null;
  file_sha256: string | null;
  row_count: number;
  valid_row_count: number;
  invalid_row_count: number;
  session_count: number;
  issues: ImportIssue[];
}

export interface ImportResponse { dataset: Dataset; summary: ImportSummary }

export interface DatasetSession {
  id: string;
  source_session_id: string | null;
  synthetic_session: boolean;
  first_source_row: number;
  first_source_timestamp: string | null;
  last_source_timestamp: string | null;
  turn_count: number;
  metadata: JsonObject;
}

export interface DatasetTurn {
  id: string;
  turn_index: number;
  source_row_number: number | null;
  source_time_raw: string | null;
  source_timestamp: string | null;
  query: string;
  metadata: JsonObject;
}

export interface Run {
  id: string;
  dataset_id: string | null;
  run_type: "DATASET_INSPECTION" | "STABILITY_QUERY" | "STABILITY_SESSION" | "STABILITY_DATASET";
  status: RunStatus;
  config_snapshot: JsonObject;
  total_sessions: number;
  completed_sessions: number;
  total_turns: number;
  completed_turns: number;
  fallback_count: number;
  error_count: number;
  infrastructure_error_count: number;
  git_commit_sha: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested_at: string | null;
  heartbeat_at: string | null;
  failure_code: string | null;
  metadata: JsonObject;
}

export interface RunSession {
  id: string;
  run_id: string;
  dataset_session_id: string | null;
  source_session_id: string | null;
  repeat_index: number;
  evaluation_session_key: string;
  status: RunStatus;
  turn_count: number;
  fallback_count: number;
  error_count: number;
  infrastructure_error_count: number;
  total_latency_ms: number | null;
  first_divergent_turn: number | null;
  first_divergent_stage: StageName | null;
  first_query: string | null;
  synthetic_session: boolean;
  synthetic_label: string | null;
  started_at: string | null;
  finished_at: string | null;
  metadata: JsonObject & { stability?: StabilitySummary };
}

export interface RunTurn {
  id: string;
  turn_index: number;
  raw_query: string;
  actual_answer: string | null;
  actual_intent: string | null;
  rewritten_query: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
  status: string;
  infrastructure_error: boolean;
  error_code: string | null;
  total_latency_ms: number | null;
}

export interface RunSessionDetail { id: string; status: string; repeat_index: number; turns: RunTurn[] }

export interface StageResult {
  stage_name: StageName;
  stage_order: number;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "SKIPPED" | "ERROR";
  input_hash: string | null;
  output_hash: string | null;
  duration_ms: number | null;
  input_data: JsonObject | null;
  output_data: JsonObject | null;
  metrics: JsonObject | null;
  error_code: string | null;
  error_data: JsonObject | null;
}

export interface TraceTurn extends RunTurn {
  normalized_query: string | null;
  history_before_hash: string | null;
  history_after_hash: string | null;
  intent_score: number | null;
  selected_context_hash: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface TurnTrace { turn: TraceTurn; stages: StageResult[] }

export interface StabilitySummary {
  first_divergent_turn: number | null;
  first_divergent_stage: StageName | null;
  fallback_count: number;
  fallback_rate: number;
  incomparable_turn_count: number;
  unique_variants: Record<string, string[]>;
  variant_counts: Record<string, number>;
}

export interface IdResponse { id: string; status: string }

export interface SseEvent {
  id?: string;
  event: string;
  data: JsonObject;
}
