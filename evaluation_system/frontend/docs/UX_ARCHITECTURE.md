# RagBot Eval UX Architecture

Status: Stage 8 design exploration

Primary target: desktop engineering workstations at 1440px to 1920px

Prototype data: realistic mock values only

## Product statement

RagBot Eval is an internal AI quality and observability workstation. It helps an AI engineer move through one stable hierarchy:

```text
Run
  Session / repetition
    Turn
      Pipeline stage
        Exact stored input, output, hashes, timing and metadata
```

The product observes the real RagBot runtime. It does not introduce another chatbot runtime. PostgreSQL remains authoritative for datasets, execution state and results. Live updates are a projection of PostgreSQL state through SSE.

## Design read and direction

This is a dense enterprise engineering application for AI engineers. The visual language is a calm graphite flight recorder with one cyan-teal accent. Evidence and execution order create the identity, not decoration.

Working design dials from the two frontend design skills:

- Design variance: 3/10. The shell and tables remain predictable under operational pressure.
- Motion intensity: 2/10. Motion communicates live state and selection only.
- Visual density: 9/10. Thin dividers and compact rows replace large card collections.

The distinctive element is the execution spine: a continuous nine-stage rail that exposes state, duration and hash lineage, then controls a specialized stage inspector. It is specific to the evaluation domain and becomes the visual signature of the Run Inspector.

The prototype uses native HTML, CSS and JavaScript because this is an isolated design artifact. No design system or new dependency is added. The later production implementation can reuse the existing React, Phosphor, TanStack Query and TanStack Table stack.

### Visual character

- One locked dark theme using graphite and deep navy layers.
- Cyan-teal is reserved for active, live and current selection.
- Green means successful completion.
- Amber means warning, fallback or divergence.
- Red means error or failure.
- Slate means neutral, pending or unavailable.
- Borders and surface shifts define hierarchy. Shadows are limited to overlays.
- Corners use a 6px and 8px system.
- Persian uses the existing local Vazirmatn files.
- Technical values use an isolated monospace stack.

The deliberate aesthetic risk is a compact, border-led three-pane workspace with almost no conventional cards. This makes the product feel closer to an instrument than an admin dashboard while remaining calm and readable.

## Current frontend audit

The current production frontend already contains useful contract-oriented pieces:

- React 19 and Vite
- TanStack Query and Table
- Phosphor icons
- local Vazirmatn font files
- typed API client for datasets, runs, sessions, turn traces and system capabilities
- custom fetch-stream SSE parser and reconnecting run hook
- early specialized stage views for normalization, intent, rewrite, retrieval, rerank, context, prompt and generation
- dataset and stability inspectors

Important issues for later implementation:

- The backend canonical contract has nine stages, but the current frontend `StageName` type and rail omit `HISTORY`.
- The current rail order places `INTENT` before `REWRITE`. The backend canonical order is `NORMALIZATION`, `HISTORY`, `REWRITE`, `INTENT`, `RETRIEVAL`, `RERANK`, `CONTEXT_SELECTION`, `PROMPT_BUILD`, `GENERATION`.
- Current rerank UI field aliases do not fully match the stored answer-context fields. The backend stores `original_rrf_rank`, `reranker_rank`, `hybrid_score` and `reranker_score`.
- The current service bar still describes Redis, but Stage 8 architecture and live events are PostgreSQL-backed. The future shell must not imply Redis is authoritative.

These findings do not change production code during Stage 8.

## Information architecture

Use exactly six persistent primary areas in the right sidebar:

1. Overview
2. Datasets
3. Runs
4. Stability
5. Pipeline
6. System

The Persian visible label may be paired with the English product-area name as a small utility label. No other destination belongs in primary navigation.

The contextual top bar contains:

- current area and page title
- environment
- compact Eval API, PostgreSQL, Worker and RagBot connection signals when supportable
- SSE live or reconnect state while a run is open

It does not duplicate the sidebar or become a second navigation system.

## Direction and bidi strategy

The application root uses `dir="rtl"`. Sidebar placement, reading order, labels, Persian conversation content and action placement follow RTL expectations.

Technical content is rendered as an explicit LTR island with `dir="ltr"`, a monospace font and `unicode-bidi: isolate`. Apply this to:

- UUIDs and run IDs
- Git SHA values and hashes
- model identifiers
- stage names
- JSON and code-like values
- timestamps and durations
- scores and rank notation
- file paths and error codes

Do not rely on `dir="auto"` for mixed hash or identifier strings. Truncated identifiers expose the full value through title text, copy action or detail view.

The Run Inspector workspace uses explicit grid areas so physical panel placement is stable:

```text
LEFT                         CENTER                         RIGHT
+--------------------------+------------------------------+------------------+
| Selected stage inspector | Selected turn and answer     | Session navigator|
| Structured / Raw JSON    | User, rewrite, response      | Repeat and turns |
+--------------------------+------------------------------+------------------+
```

Each panel returns to RTL internally. Tables may keep RTL column flow, while individual technical cells remain LTR.

## Screen architecture

### Overview

Answer one question: what is happening with evaluation now?

Order:

1. compact current-state band for active, queued, completed and failed runs
2. fallback and error rates derived from loaded run counters
3. current and recent runs
4. system connection summary
5. recent stability findings already present in loaded run-session summaries

Do not present long-term trend charts until an aggregate or time-series contract exists. Cross-run totals that require loading every run should be treated as client-side derived and clearly scoped to the loaded result set.

### Datasets

Use a dense browser rather than a large upload hero.

- Compact `Import file` action opens or reveals the four-step flow: choose, detect, validate, import.
- Dataset summary shows filename, source type, file hash, import timestamp, rows, valid rows, invalid rows and sessions.
- Session browser uses current dataset session and turn endpoints.
- Main rows show session, turn, timestamp, query, validation and source row where available.
- Selecting a session reveals the ordered conversation sequence.
- Import warnings are available in the import response. Persisted warning history must not be assumed unless present in dataset metadata.

### Runs

The entry screen is an operational table with filters for status, run type, dataset, date, error presence and fallback presence.

Columns:

- run ID
- dataset
- type
- status
- session and turn progress
- fallbacks
- errors
- infrastructure errors
- duration
- Git SHA
- created and started time

Running rows animate only the small live indicator and progress transition. Selecting a row opens the Run Inspector.

### Run Inspector

This is the flagship screen and should receive the largest implementation budget.

#### Header

The header keeps identity and operational facts visible without using large cards:

- full run ID with a safe truncated display
- status
- dataset
- run type
- Git SHA
- duration derived from timestamps while running or completed
- knowledge sources from `config_snapshot.retrieval.knowledge_sources` when present
- session and turn progress
- fallback, error and infrastructure-error counts

#### Execution rail

The nine-stage rail is a technical timeline, not a flowchart. Stage sequence is numbered because the order is real and diagnostically important.

Every stage segment shows:

- English canonical stage name
- completed, running, skipped or error state using shape, text and color
- duration
- abbreviated input and output hashes
- selection state

If a stage is not yet persisted, show a neutral pending skeleton in its exact final footprint. Do not infer completion from the selected turn status.

#### Three-pane workspace

- Right panel: sessions, repetitions and turns. It supports scanning status, fallback, error and duration without opening every turn.
- Center panel: readable conversation evidence. The answer is visually separate from diagnostic facts. Previous and next turn controls preserve the current session.
- Left panel: specialized output for the selected stage. `Structured view` is primary. `Raw JSON` is a secondary advanced tab.

The user should be able to inspect a complete execution without navigating away.

#### Selected turn summary

Always make these values reachable in the center panel or its metadata strip:

- raw query
- normalized query
- rewritten query
- detected intent
- intent confidence when present
- final answer
- total latency
- fallback state and reason
- error and infrastructure-error state
- selected context hash

### Stability

Support `STABILITY_QUERY`, `STABILITY_SESSION` and `STABILITY_DATASET` through one comparison workspace.

The repetition matrix uses logical turns or sessions as rows and repetition indexes as columns. Cells carry both a symbol and text-accessible state:

- `=` identical
- `≠` divergent
- `!` error
- `?` incomparable

Selecting a divergent cell opens an A/B comparison. The first divergent turn and first divergent stage remain pinned above the comparison. Only differing rows receive strong amber emphasis; equal rows remain visually quiet.

Comparison rows can include normalized query, rewrite, intent, retrieval order hash or candidate order, reranked order, selected context hash, prompt hash, answer hash and answer. Render only values present in trace or stored summaries.

### Pipeline

This is a global technical trace workspace. The proposed filters are run ID, session, turn, stage, intent, error and fallback. A selected result reuses the execution rail and stage inspector.

Global trace search is a future backend requirement. The existing API can open a known run, session and turn, but it does not expose a global trace query endpoint. The preview labels this interaction as conceptual.

### System

Show only signals that can be supported:

- Eval API request reachability
- PostgreSQL migration state and initialization availability
- background execution capability
- current run heartbeat where a run is open
- RagBot datasource request success as a limited connectivity signal
- exposed concurrency, file and repeat capabilities

A direct Worker health state, global queue depth and dedicated RagBot health endpoint require future backend support. CPU, GPU, memory and model-serving telemetry are out of scope until exposed.

## Specialized pipeline stage views

Every stage view begins with a compact metadata strip for status, duration, input hash and output hash. Error or skipped state is then shown before the specialized body.

### 1. NORMALIZATION

Primary content is a side-by-side original and normalized query comparison. Highlight character-level changes only when meaningful. Show a `no textual change` state when equal.

Current trace fields:

- `input_data.raw_query`
- `output_data.normalized_query`
- stage hashes and duration

### 2. HISTORY

Show messages used as an ordered user/assistant transcript. Long history collapses after a few messages without hiding the count. Show real-history state, source and number of messages.

Current trace fields:

- `output_data.real_history_exists`
- `output_data.messages_used`
- `output_data.formatted_history`
- `metrics.history_message_count`
- `metrics.source`
- turn `history_before_hash` and `history_after_hash`

The turn history hashes are conversation-state evidence. The stage input and output hashes are hashes of the stage payload. Label them separately.

### 3. REWRITE

Use a clear before and after comparison:

- normalized current query
- available history or context summary
- rewritten standalone query
- classification query
- rewrite-used flag, skip reason or fallback reason when stored

Do not claim a generated context summary exists unless present in the payload.

### 4. INTENT

Use a compact confidence number and thin line, not a decorative gauge. Show selected intent, classifier input, stored classifier details and effective threshold. Do not generate a probability distribution that is not present.

Current sources include `turn.actual_intent`, `turn.intent_score`, intent output details and `metrics.effective_threshold`.

### 5. RETRIEVAL

Title the main table `Search results before reranking`.

Show all `output_data.candidates` with:

- `rank` and `original_rrf_rank`
- `chunk_id`
- `retrieval_score`
- optional BM25 and semantic scores in secondary columns or details
- source from candidate metadata
- category or page when present in metadata
- content preview

Selecting a row opens the full stored `content` and metadata in the same pane. The inspector must not hide candidates merely because they were not later selected.

### 6. RERANK

Default to final reranked order with an optional original-order toggle. Compare:

- `original_rrf_rank`
- `reranker_rank`
- `chunk_id`
- source
- `hybrid_score`
- `reranker_score`
- selected state
- signed rank movement

Examples use `#8 → #1 ↑7`, `#1 → #4 ↓3` and `#2 → #2 =`. Up, down and unchanged each combine symbol, number and semantic styling. Do not expect `input_rank`, `output_rank` or `score` for the answer-context rerank path; those names belong to the auxiliary related-question rerank payload.

Selecting a rerank row reveals its stored content, metadata and rerank input text where present. Do not invent reranker scores for skipped or missing output.

### 7. CONTEXT_SELECTION

Lead with the distinction `Actually selected for generation`.

Show each selected chunk in output order with chunk ID, reranked rank when it can be joined client-side, source, available score and full stored content. Show selected count and `metrics.selected_context_hash`.

The selected context output may be either an aggregate string or structured results. The renderer must tolerate both shapes and fall back to a readable preformatted content block.

### 8. PROMPT_BUILD

Primary view is an ordered message stack using only stored content:

- system message
- user prompt
- context from input data when useful
- recent history from input data when useful

Show prompt source, prompt version, prompt hash and message count when available. Actual token metadata may be shown only if a later trace stores it. The full prompt remains collapsed by default. Raw JSON is the advanced tab.

### 9. GENERATION

The final answer is the dominant element. Beside it show generation duration, answer hash, fallback state, fallback reason and recorded generation metadata such as model and settings.

Grounded sources can be joined from the selected context data because generation output itself currently contains the answer, not a source mapping. Label this as `selected sources used for context`, not answer-level citations, unless a future contract provides exact citation mapping.

## Component inventory

### Shell

- `ApplicationShell`
- `RightSidebar`
- `ContextTopbar`
- `EnvironmentLabel`
- `ConnectionSummary`
- `Breadcrumb`

### Run inspection

- `RunIdentityHeader`
- `RunProgressSummary`
- `ExecutionRail`
- `StageSegment`
- `SessionTurnNavigator`
- `SessionGroup`
- `TurnRow`
- `TurnConversation`
- `TurnMetadataStrip`
- `StageInspectorFrame`
- one specialized stage view for each of the nine canonical stages
- `RawJsonView`
- `HashValue`
- `StatusLabel`
- `ErrorEvidence`

### Data and comparison

- `DenseDataTable`
- `FilterBar`
- `DatasetSummary`
- `CompactUploadFlow`
- `ConversationSequence`
- `RepetitionMatrix`
- `ExecutionDiff`
- `RankMovement`
- `CandidateContentDrawer`
- `ServiceStateList`

Prefer rows, dividers and split panes over generic card wrappers. Use a card only where a genuinely separate object benefits from containment.

## Real-time behavior

The PostgreSQL-backed SSE stream sends an authoritative `snapshot` immediately, then transient events derived from projection changes:

- `session_started`
- `turn_started`
- `stage_completed`
- `turn_completed`
- `session_completed`
- `progress`
- `run_completed`
- `run_failed`
- `run_cancelled`

Reconnect contract:

- `snapshot` is authoritative.
- Historical transient events are not replayed.
- `Last-Event-ID` is tolerated but is not a durable replay cursor.
- After reconnect, replace local projection assumptions with the new snapshot and refetch affected run, sessions and open trace data.

Connection labels:

- Connected: small cyan `LIVE` signal.
- Reconnecting: amber inline status. Preserve the last authoritative data.
- Disconnected: neutral or red signal based on error, with an explicit retry action after the normal retry window.
- Recovered from snapshot: brief non-blocking confirmation, then return to `LIVE`.

Only transform, opacity and progress width may animate. Do not flash completed stages. A new stage row can fade in once. Respect `prefers-reduced-motion`.

## Loading, empty, error and reconnect states

### Loading

- Shell and navigation render immediately.
- Tables use row skeletons with final row height.
- Run Inspector preserves pane dimensions while a trace loads.
- Stage rail skeletons occupy all nine final positions.
- No page-wide spinner after the shell is available.

### Empty

- Datasets: explain accepted files and provide `Import file`.
- Runs: explain that a dataset and knowledge source are required, then link to Datasets.
- Stability: explain that two or more repetitions are required.
- Trace stage: distinguish `not yet persisted`, `skipped by runtime` and `completed with empty output`.

### Error

- Request errors remain in the affected pane or table.
- Turn and stage infrastructure errors show the safe error code in LTR.
- Preserve readable partial evidence when one stage fails.
- A run failure remains separate from an SSE connection failure.

### Reconnect

- Do not clear current evidence while reconnecting.
- Disable only actions that require a confirmed live connection.
- On snapshot recovery, reconcile progress and open entities instead of playing missed animation.

## Design tokens

Prototype values:

```css
:root {
  --background: #070d13;
  --surface-1: #0b131c;
  --surface-2: #0f1924;
  --surface-3: #14212d;
  --border-subtle: #1d2b38;
  --border-strong: #304252;
  --text-primary: #e8eef2;
  --text-secondary: #a7b4be;
  --text-muted: #71808c;
  --accent: #48b7c7;
  --success: #58ba8c;
  --warning: #d6a552;
  --danger: #e26f78;
  --info: #6ca7d9;
  --radius-sm: 6px;
  --radius-md: 8px;
}
```

Spacing follows a compact 4px base: 4, 8, 12, 16, 24 and 32. Table rows target 36px to 42px. Primary interactive targets target at least 32px in dense desktop contexts, with clear focus indication and larger targets for primary actions.

Typography roles:

- Persian body and UI: existing local Vazirmatn, 400 and 600.
- Technical values: system monospace stack.
- Page title: 22px to 26px, semibold.
- Section title: 13px to 16px, semibold.
- Body: 11px to 13px with increased Persian line height.
- Dense table and metadata: 9px to 11px.

## Responsive behavior

### 1440px to 1920px

- Persistent 216px right sidebar.
- Full nine-stage rail.
- Three-pane Run Inspector with left stage inspector, center turn evidence and right navigator.
- Dense tables remain in place with optional sticky headers.

### Around 1280px

- Sidebar contracts to approximately 196px.
- Navigator contracts to approximately 230px.
- Low-priority run-header fields may collapse into a details disclosure.
- The three-pane hierarchy remains visible when practical.
- Tables use contained horizontal scrolling rather than removing columns silently.

### Below approximately 1120px

- Sidebar may collapse to a compact rail.
- Turn and navigator remain side by side.
- Stage inspector moves below as a full-width tab panel or opens as a left drawer.
- The execution rail remains horizontally scrollable with all nine stages.

No mobile-specific product design is included in this stage.

## Accessibility and usability

- State is always represented by text plus shape or symbol plus color.
- Focus rings use the cyan accent and remain visible on every surface.
- Row selection and stage selection use borders or inset rules, not color alone.
- Reduced motion removes live pulse and all nonessential transitions.
- Persian text uses comfortable line height even in dense panels.
- Table headers remain visible and columns have explicit labels.
- Long IDs truncate visually but expose their full value.
- Raw JSON is keyboard scrollable and explicitly LTR.
- Rank movement has arrows and signed numbers.
- Matrix cells have accessible labels such as `Repeat 2, turn 3, error`.

## Current API to screen data map

Legend:

- **Available now**: directly returned by a current contract.
- **Derived client-side**: computed or joined from current responses.
- **Future backend requirement**: no current endpoint or durable field supports it.

| Screen / need | Source | Status | Notes |
|---|---|---|---|
| Database state | `GET /system/database-status` | **Available now** | State, revisions, missing objects, init permission and safe error code. |
| File limits and concurrency | `GET /system/capabilities` | **Available now** | File types, upload bytes, rows, concurrency, repeat max and feature flags. |
| RagBot datasource list | `GET /datasources` | **Available now** | Successful response is a limited RagBot connectivity signal, not a complete health check. |
| Dataset browser and summary | `GET /datasets`, `GET /datasets/{id}` | **Available now** | Includes file hash, row counts, session count, type and creation time. |
| Import validation summary | `POST /datasets/import` | **Available now** | Includes import issues in the immediate response. Historical issues are not a dedicated endpoint. |
| Dataset session sequence | `GET /datasets/{id}/sessions`, `GET /datasets/sessions/{id}/turns` | **Available now** | Supports source session, synthetic state, ordering, query, timestamps and source row. |
| Runs operational table | `GET /runs` | **Available now** | Contains status, progress counts, errors, Git SHA and timestamps. Dataset filename requires a client join. |
| Run duration | run timestamps | **Derived client-side** | Use current time minus `started_at`, or `finished_at` minus `started_at`. |
| Knowledge sources | `run.config_snapshot` | **Available now when snapshot populated** | Provisional and runtime snapshot shape may vary. Treat missing data as unavailable. |
| Run session navigator | `GET /runs/{id}/sessions` | **Available now** | Repetition, counts, first query, latency, first divergence and metadata. |
| Turn list and answer | `GET /run-sessions/{id}` | **Available now** | Raw query, answer, intent, rewrite, fallback, error and latency. |
| Complete stage trace | `GET /run-turns/{id}/trace` | **Available now** | Turn summary plus stored stage input, output, metrics, hashes, timing and errors. |
| Retrieval table | retrieval `output_data.candidates` | **Available now** | All stored candidates include content and metadata. |
| Rerank movement | retrieval candidates plus rerank `output_data.rankings` | **Derived client-side** | Join on chunk ID and compare `original_rrf_rank` with `reranker_rank`. |
| Selected context source and score | context output plus retrieval/rerank outputs | **Derived client-side** | Join selected chunk IDs to stored candidate rows. |
| Answer grounded sources | context selection plus generation output | **Derived client-side** | This proves selected context, not exact answer citation alignment. |
| Stability first divergence | run-session fields and `metadata.stability` | **Available now** | Backend is authoritative for first turn and stage. |
| Repetition matrix | sessions, turns and traces | **Derived client-side** | Existing frontend already loads attempts and compares hashes. Large runs may need later backend support. |
| Overview rates | loaded run counters | **Derived client-side** | Scope and time window must be visible. No current analytics aggregate endpoint. |
| Live run state | `GET /runs/{id}/events` | **Available now** | PostgreSQL snapshot plus transient projection events. |
| SSE replay | none | **Future backend requirement** | Current `Last-Event-ID` is not durable replay. Design does not depend on replay. |
| Global trace search | none | **Future backend requirement** | Current navigation requires known run, session and turn IDs. |
| Global queue depth | none | **Future backend requirement** | Pending run counts can be derived from a loaded runs list, not authoritative queue depth. |
| Direct worker health | none | **Future backend requirement** | `background_execution_available` is capability configuration. `heartbeat_at` is run-specific. |
| Dedicated RagBot health | none | **Future backend requirement** | Datasource success is only an indirect signal. |
| CPU, GPU and memory telemetry | none | **Future backend requirement** | Do not show in production UI until exposed. |
| Token usage and exact token count | none in current stage trace | **Future backend requirement** | Do not estimate in the primary product view. |

## Implementation sequence for a later stage

1. Correct the shared frontend stage contract to include `HISTORY` and canonical ordering.
2. Introduce semantic tokens and the persistent RTL shell without changing data behavior.
3. Build the dense Runs table and run route hierarchy.
4. Implement the Run Inspector layout and session/turn navigation.
5. Implement the nine-stage rail and shared inspector frame.
6. Port specialized views in order: retrieval, rerank, context selection, generation, history, rewrite, intent, normalization and prompt build.
7. Add authoritative snapshot reconciliation to the current SSE hook and present reconnect states.
8. Build Stability around the existing summary and trace contracts.
9. Reshape Datasets, Overview and System using only current fields.
10. Keep Pipeline global search visibly limited until a backend contract exists.
11. Run keyboard, bidi, contrast, reduced-motion and 1280px layout reviews.

Each production implementation slice should preserve API behavior and be reviewed with real trace fixtures before the next slice begins.

## Prototype notes

Open `evaluation_system/frontend/design-preview/index.html` directly in a browser. The artifact is intentionally outside the Vite production entry and does not call any API.

The prototype demonstrates:

- all six primary areas
- persistent right navigation and contextual top bar
- flagship Run Inspector
- all nine clickable stage outputs
- retrieval candidate content inspection
- rerank old-rank to new-rank movement
- selected generation context
- final generated answer and selected sources
- session and turn selection
- lightweight Overview, Dataset, Stability, Pipeline and System screens

Every numeric value, hash, identifier, answer and service state in the preview is design mock data.
