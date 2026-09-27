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
