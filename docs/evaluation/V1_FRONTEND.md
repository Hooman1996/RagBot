# RagBot Evaluation V1 frontend

## Outcome

The evaluation console is a standalone React 19, TypeScript, and Vite source application at `evaluation_system/frontend`. It does not import or modify the chatbot Jinja templates, `static`, or `kb_manager.py`. Its static build is served by the existing RagBot FastAPI app at `/evaluation`.

The interface is Persian-first and uses `dir="auto"` for customer and model content. Technical identifiers, hashes, event names, and fingerprints use left-to-right presentation. Login uses the existing RagBot username/password endpoint. No evaluation token or separate evaluation identity store exists.

## Design system

The console is a dense, regulated diagnostic cockpit rather than a marketing dashboard.

- Visual tokens use cool graphite surfaces with one cobalt interaction accent.
- Vazirmatn Regular and Semibold are copied from the repository's existing OFL-licensed vendor bundle and emitted as local build assets. System Persian-capable fonts remain fallbacks.
- Phosphor icons are compiled into the JavaScript bundle. No icon or SVG service is contacted.
- The shape system uses 12 px surfaces, 8 px controls, and 6 px compact status elements.
- Motion is limited to state feedback, progress width, and skeleton loading. Reduced-motion preferences are honored.
- Both system light and dark color schemes are defined with the same information hierarchy and WCAG-oriented contrast.
- The distinctive element is the eight-stage provenance rail. It encodes the real pipeline order and stage state rather than adding decorative dashboard chrome.

The implementation applies `design-taste-frontend` to accessibility, asset locality, theme consistency, interaction states, responsive collapse, and anti-clutter review. The skill explicitly excludes dense dashboards, so TanStack Table and product-specific native CSS own the data interface. `frontend-design` guided the subject-specific trace rail, functional copy, restrained palette, and one-signature-element rule.

## Application structure

```text
evaluation_system/frontend/
  public/fonts/                 locally bundled Vazirmatn files and OFL license
  scripts/audit-offline.mjs     source and dist public-reference audit
  src/
    api/                        typed HTTP client and streaming-fetch SSE parser
    app/                        providers, in-memory auth, application shell
    components/
      database-setup/           access and migration gates
      dataset-import/           shared CSV/XLSX importer UI
      runs/                     live progress and persisted recent runs
      session-results/          TanStack session table and nested turns
      trace/                    shared stage rail, trace, and stage inspectors
      ui/                       owned primitive components and states
    features/
      dataset-inspector/
      stability-inspector/
    hooks/                      URL state and reusable SSE lifecycle
    styles/                     semantic tokens and responsive layout
    test/                       Vitest and Testing Library coverage
    types/                      backend API contract types
  package.json
  package-lock.json
  vite.config.ts
```

No React Router dependency is required. The two primary panels and active run are represented by `panel` and `run` query parameters. This means a refresh can reopen persisted run state without requiring SPA route rewrites. Authentication is intentionally not persisted.

## Database setup gate

After an existing RagBot user signs in through `POST /api/login`, the application calls `GET /api/v1/evaluation/system/database-status`.

- `READY` unlocks the inspectors.
- `NOT_INITIALIZED` explains the isolated evaluation tables and offers **Create Evaluation Tables** only when the backend reports `allow_initialize=true`.
- `UPGRADE_REQUIRED` shows current and required revisions and offers **Upgrade Evaluation Tables** under the same gate.
- `ERROR` shows a safe code and retry action.
- When initialization is disabled, the UI provides the `EVAL_ALLOW_DB_INIT=true` operator instruction and does not show an executable migration action.

The confirmation dialog requires the exact backend value `CREATE_EVALUATION_TABLES`. It sends no SQL and exposes no drop action.

## Dataset Inspector

The Dataset Inspector provides:

- drag/drop or file selection for `.csv` and `.xlsx`;
- local filename and size display before upload;
- backend-reported limits from `/system/capabilities`;
- import totals, valid/invalid counts, detected sessions, multi-turn counts, single-query counts, SHA256 prefix, and all parser issues;
- explicit explanation of session grouping and blank-session isolation;
- required current knowledge datasource selection;
- durable run creation and live SSE progress;
- recent runs that can be reopened from PostgreSQL-backed REST state;
- one TanStack Table row per run session, with search, status filter, fallback filter, and pagination;
- nested session, turn, and trace expansion.

Turn trace views include Input/History, Normalization, Intent, Rewrite, Retrieval, Reranking, Selected Context, Final Prompt, Generation, and Timing/Errors. Retrieval rows expand to content and metadata. Reranking shows input/output rank and promotion/demotion without a quality claim. Prompt, context, query, answer, and chunk content are rendered as escaped text only. No raw HTML path exists.

Semantic fallback and infrastructure failure are separate visual states. A successful textual difference is labeled **Diverged**, never **Incorrect**.

## Stability Inspector

Input modes are:

- one user query;
- an ordered user-only conversation builder with add, remove, and reorder controls;
- CSV/XLSX through the same `DatasetImport` component and backend importer as Dataset Inspector.

Repeat count is constrained to the backend contract range of 2 through 100. The UI explains that generated assistant messages become history only inside the current repetition and that every repetition starts empty.

Results group run sessions by logical dataset session. They display repetitions, turns, fallback rate, unique answer count, and backend-computed first divergent turn/stage. Expanding a logical session lazily loads durable turn traces, then provides:

- per-turn normalization, intent, rewrite, retrieval, rerank, context, prompt, and answer variant counts;
- an attempts table with fingerprints, fallback, and latency;
- attempt expansion through the same `TurnTrace` used by Dataset Inspector;
- a selectable two-repeat comparison whose canonical first divergence is the backend value.

## API endpoints consumed

The typed client in `src/api/client.ts` is the only HTTP access layer.

- `GET /system/database-status`
- `POST /system/database-initialize`
- `GET /system/capabilities`
- `GET /datasources`
- `POST /datasets/import`
- `GET /datasets`
- `GET /datasets/{id}`
- `GET /datasets/{id}/sessions`
- `GET /datasets/sessions/{id}/turns`
- `DELETE /datasets/{id}`
- `POST /runs`
- `GET /runs`
- `GET /runs/{id}`
- `GET /runs/{id}/sessions`
- `GET /run-sessions/{id}`
- `GET /run-turns/{id}/trace`
- `POST /runs/{id}/cancel`
- `DELETE /runs/{id}`
- `GET /runs/{id}/events`
- `POST /stability/manual`

The default base is the same-origin relative path `/api/v1/evaluation`. A connected build environment can set `VITE_EVALUATION_API_BASE` to an approved internal base. Public hosts must not be used.

## SSE behavior

`src/api/sse.ts` parses event IDs, named events, comments, and multi-line data. `useRunEvents` uses same-origin streaming `fetch`, stores the latest event ID in memory, supplies `Last-Event-ID` on reconnect, aborts only the browser stream on navigation/unmount, and uses bounded reconnect delay.

SSE is an invalidation and progress channel. Events refetch run/session REST queries. Disconnecting the page does not cancel the backend job. Terminal truth always comes from PostgreSQL-backed REST responses.

## Build and development

From the repository root:

```bash
cd evaluation_system/frontend
npm ci
npm run build
```

Normal integrated development commands:

```bash
cd /root/projects/faq/evaluation_system/frontend
npm ci
npm run build
cd /root/projects/faq
python main.py
# In a second terminal:
evaluation_system/backend/scripts/start_worker.sh
```

Open `http://<ragbot-host>:<ragbot-port>/evaluation`. A standalone Vite development server remains optional for frontend-only work; normal operation does not require a second evaluation FastAPI process.

For optional Vite development, start `python main.py` first and then run `npm run dev`. Vite reads the root `.env` and proxies both `/api/login` and `/api/v1/evaluation` to the integrated RagBot app using `API_PORT` (default `8080`). `EVAL_API_DEV_PROXY` may override that internal development target. It must point to the RagBot app, not the obsolete standalone evaluation API on port `8090`.

To compile a different approved internal API base:

```bash
cd evaluation_system/frontend
npm ci
VITE_EVALUATION_API_BASE=/api/v1/evaluation npm run build
```

## Verification

The frontend validation command is:

```bash
cd evaluation_system/frontend
npm run validate
```

It runs Vitest, TypeScript/Vite production build, and the offline reference audit. Unit/component coverage includes the database gate and initialization confirmation, API failure recovery, dataset upload summary and warnings, session/turn/trace expansion, manual conversation editing, repeat validation, backend-canonical divergence display, fallback/error separation, SSE parsing, and live hook updates.

No locally installed Playwright or Chromium binary was present, so no browser smoke test was run and no browser package was installed.
