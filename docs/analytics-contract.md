# Main chatbot analytics contract (Step 3)

The dashboard reports the existing `queries` records. Timestamps are stored as
naive UTC values (`datetime.utcnow()` in the query write path), in PostgreSQL
`timestamp without time zone` columns. All reporting calendar dates, weekdays,
and hours use **UTC**. The selected 7, 14, or 30 day window starts at 00:00 UTC
on the first calendar day and ends at the request's UTC snapshot time. The API
returns both boundaries and `timezone: "UTC"`. Every selected-window panel uses
`queries.created_at >= start AND created_at < end`; no future rows are counted.

| Display | Source and calculation | Incomplete queries / empty state |
| --- | --- | --- |
| Queries | Count of all query rows in the selected window. | Pending and failed count; show `0` if there are no rows. |
| Users who queried | `COUNT(DISTINCT queries.user_id)` in the window. | All states count; show `0` for no rows. |
| Average completion duration | Mean seconds of `completed_at - created_at` for `status = 'completed'` and nonnegative, non-null timestamp pairs. Show measured count and completed count. | Other states excluded. No valid pairs: `null` and “Unavailable: no completed queries with valid timestamps”; never use `updated_at`. |
| Rated responses | Helpful plus unhelpful query votes in the window; denominator is all queries in the window. | Unrated includes NULL votes in any state. Show `0 / total` when the window has rows; show `0 / 0` for no rows. |
| Indexed documents | Count of documents with `processing_status = 'completed'` at request time. **Global**, independent of the selected window. | Show `0` when none; this is a record count, not uptime. |
| Queries per day | Count query rows by UTC creation date, including zero days within the selected window. | All states count. With no rows, display a no-activity message instead of a zero line. |
| Users per day | Distinct `queries.user_id` by UTC creation date, including zero days. | All states count. With no rows, display no activity. Session creation dates are irrelevant. |
| Feedback outcomes | Helpful (`is_helpful = 1`), unhelpful (`= 0`), and no feedback (`IS NULL`), among selected-window queries. Rated-response count is helpful + unhelpful. | All states are in the denominator. If no queries, display no activity. This is not a 1–5 rating. |
| Conversation depth | Group by `chat_session_id` for selected-window queries with a session, then bucket the in-window count per session into 1, 2–4, 5–9, 10+. | All states count. Queries without a session are excluded and reported as a count. A session spanning the window boundary is counted **only by its queries inside the window**, once in one bucket. No session queries: empty state. |
| Completion duration buckets | Count valid completed query durations in seconds: `<2`, `2–5`, `5–10`, `10–20`, `20+`. Denominator is valid completed durations; the API also gives completed rows and excluded rows. | Pending/failed and missing or negative timestamps excluded. No valid durations: unavailable state with the reason. |
| Query states | Counts of actual `completed`, `pending`, and `failed` rows in the selected window; unexpected/non-null values and NULL are combined as “other” only when present. Zero-count states are omitted. | No query rows: no-activity state. |
| Weekday × hour activity | Seven ISO weekdays (Monday first) by 24 UTC creation hours. Cell counts are queries, with row and grand totals. | All states count. No query rows: no-activity state; the accessible text summary contains each day and hour count when populated. |
| Weekly comparison | **Independent of the selected filter**: each UTC weekday's query count in the last seven calendar days (including today to snapshot time) against the preceding seven full calendar days. | All states count. If both weeks have no queries, show no activity. The title and metadata state this independent window. |

SQL only returns counts, averages, and date/hour/status aggregates. It never
selects query text, answers, customer identifiers, document content, or
`retrieved_documents`. A failed API request is a load error, not a zero metric.

## Local browser smoke procedure

1. Use the project's Python environment and configured **development** database.
   Start the existing app locally with:
   ```sh
   WEB_ENVIRONMENT=development WEB_COOKIE_MODE=local-http WEB_PUBLIC_ORIGIN=http://localhost:7000 /root/miniconda3/envs/faq/bin/python -m uvicorn main:app --host 127.0.0.1 --port 7000
   ```
2. Open [http://localhost:7000](http://localhost:7000), sign in with a development
   `admin` account, and open [http://localhost:7000/analytics](http://localhost:7000/analytics).
   Confirm the timezone reads UTC, select 7, 14, and 30 days, refresh, and inspect
   chart tooltips, the rated-response denominator, completion-duration coverage,
   the observed query states, and the heatmap's keyboard-openable count table.
3. In browser network tools, confirm each filter requests
   `GET http://localhost:7000/api/analytics?days=7` (or 14/30), with only aggregate
   data. `days=8` returns 422. A signed-in `analytics_viewer` gets the dashboard
   and API; `user` and unknown roles get 403 for both. Existing chat, feedback,
   and session permissions should behave as in Step 2.
4. Confirm the page shows a load error if the API fails. The automated frontend
   test covers empty and unavailable data without changing development records.

Run focused verification with:

```sh
/root/miniconda3/envs/faq/bin/python -m pytest -q tests/test_analytics.py
node --test tests/analytics.frontend.test.cjs
```

## Step 3 repair: browser release coherence

The API metadata carries `contract_version: "main-analytics/v3"`. The protected
HTML declares the same value, and the dashboard script checks both values before
rendering. A mismatch shows one reload/cache-clear instruction; a chart-specific
construction failure names the affected card and records a non-content error in
the console. The HTML also checks the script handshake so a missing or stale
script cannot leave a half-rendered dashboard.

First-party CSS and JavaScript on `/analytics` use paths of the form
`/static/_v/<SHA-256 digest>/js/analytics.js`. The static handler verifies the
requested digest against the bytes it serves; mismatches return 404. Matching
assets are immutable under their unique URLs and carry browser Subresource
Integrity, so stale bytes under a new URL cannot execute. The protected HTML uses
`Cache-Control: no-store`; vendor Chart.js remains local. The three-column grid
is filled at desktop width, the third card spans both columns at medium width,
and all cards stack at narrow width.

For a manual browser release check at [http://localhost:7000/analytics](http://localhost:7000/analytics):

1. Sign in as a development `admin` or `analytics_viewer`. In DevTools Network,
   inspect the `/analytics` document: it must revalidate with `no-store` and its
   script URL must include `_v/<64 hexadecimal characters>/js/analytics.js`.
   Open that exact URL in DevTools Sources; it must contain
   `main-analytics/v3`, `chartFeedback`, and `chartWeekly`, and must not contain
   `Heatmap data unavailable`.
2. Confirm the fingerprinted script and CSS requests return 200 or a cached
   response for the **same fingerprinted URL**, with immutable caching. Inspect
   `/api/analytics?days=7`, `14`, and `30`: each must return `meta.contract_version`
   equal to the HTML/script version. Do not copy response bodies containing
   account data into reports.
3. For each filter, confirm all five KPIs plus Queries per day, Feedback outcomes,
   Conversation depth, Completion duration, Users who queried per day, Query
   states, Weekday comparison, and Weekday × hour activity show either a chart
   or an explicit empty/unavailable state. The heatmap's count table opens by
   keyboard. At desktop width the Query states and Weekday comparison cards fill
   their row; at medium width the third card in the depth/duration/users row
   spans both columns; at narrow width cards stack without a blank slot.
4. A forced API failure should show a load error in every card. A stale API
   contract or stale/missing script should show one version-mismatch instruction.
   Use a hard reload (`Ctrl+Shift+R`) after updating the branch.
