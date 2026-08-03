# Mass-answer user and operator manual

## What it does

`POST /api/mass-answer` answers independent spreadsheet questions through the same shared intent, rewrite-policy, LangGraph routing, hybrid retrieval, related-question reranking, context construction, prompt selection, and vLLM generation path used by web and mobile requests. Batch rows do not read chat history and do not create users, sessions, query records, messages, tickets, or agent-state records.

## Input contract

Accepted files:

- `.csv`: UTF-8 or UTF-8 with BOM. Comma, semicolon, tab, and pipe delimiters are detected. Standard quoted delimiters and multiline cells are supported.
- `.xlsx`: the first worksheet is read with preserved Unicode.

Legacy `.xls` is rejected deliberately. The old endpoint accepted its extension but the project environment has no `xlrd` reader or `.xls` writer, so it was not a reliable supported format.

The MIME type is advisory. Extension and successful content parsing determine acceptance.

Exactly one query column is required. After Unicode NFKC normalization, trimming, case folding, Arabic/Persian yeh/kaf normalization, and whitespace collapse, these names are accepted:

- `question`
- `query`
- `سوال`
- `سؤال`
- `پرسش`

All other columns are optional and preserved. Column names must be non-empty and unique after normalization. An input may not already contain reserved output columns.

The multipart `selected_docs` field must contain a JSON list with at least one document title. It applies to every row in the file; per-row document selection is not supported.

Example:

```csv
question,category
چگونه کارت بانکی جدید درخواست کنم؟,کارت
شرایط دریافت تسهیلات چیست؟,تسهیلات
```

Synthetic fixtures are in `tests/fixtures/mass_answer/sample_persian.csv` and `sample_persian.xlsx`. They contain no customer data.

## Limits and modes

| Setting | Default | Meaning |
|---|---:|---|
| `MASS_ANSWER_MAX_UPLOAD_MB` | 10 | Maximum streamed upload bytes |
| `MASS_ANSWER_MAX_ROWS` | 5000 | Maximum data rows |
| `MASS_ANSWER_DIRECT_MAX_ROWS` | 20 | Direct-download threshold |
| `MASS_ANSWER_ROW_CONCURRENCY` | 4 | Fixed batch worker count per process |
| `MASS_ANSWER_ROW_TIMEOUT_SECONDS` | 50 | Per-row semantic deadline |
| `MASS_ANSWER_JOB_RETENTION_HOURS` | 24 | Result/job expiry |

Files at or below the direct threshold are processed in the request and returned as a file. Larger files return HTTP 202 with a job ID and status/result URLs. The normal interactive 50-second deadline is never applied to the whole file.

Values are validated as positive. Batch concurrency is separate from `REQUEST_CONCURRENCY_LIMIT` and defaults to 4 rather than 32/50. Rows reuse the lifespan-owned TEI/vLLM/Qdrant/application clients. `TEI_HTTP_MAX_CONNECTIONS` and `VLLM_HTTP_MAX_CONNECTIONS` bound HTTP pools; `QDRANT_CONCURRENCY` separately bounds Qdrant; `BLOCKING_CONCURRENCY_LIMIT` bounds pandas, PostgreSQL, CPU, and filesystem work.

## Row identity and history

Every row is an independent FAQ turn. Input order is retained, but rows can execute concurrently. No session/national-code/conversation grouping columns are consumed. History is disabled and persistence is false, so one row cannot influence another. Multi-turn batch conversations are not supported by this contract; use the online session APIs when turn history is required.

Duplicate rows are not deduplicated: each source row receives its own result. Completely blank query cells are retained and classified as `invalid_input`. Numeric query values are safely converted to text. Completely blank physical CSV rows are retained by the parser.

## Output

Every original column and row remains in its original position. These columns are appended:

- `Answer (پاسخ)`
- `status`
- `error_code`
- `error_message`
- `processing_time_ms`
- `intent`
- `rewritten_query`
- `related_questions` (JSON text)

Successful rows use `status=success`. Stable failure statuses include `invalid_input`, `timeout`, `busy`, `retrieval_error`, and `internal_error`. Output contains sanitized public messages, never Python tracebacks. Unexpected tracebacks remain server-side with batch ID and row index, without query text.

CSV output uses UTF-8 with BOM and standard quoting. Excel output is `.xlsx`. Strings beginning with `=`, `+`, `-`, or `@` are prefixed with an apostrophe in both output formats to prevent spreadsheet formula execution.

## Job API

1. `POST /api/mass-answer` returns 202 for a large file.
2. `GET /api/mass-answer/jobs/{job_id}` reports queued/running/completed/failed status and row counts.
3. `GET /api/mass-answer/jobs/{job_id}/result` downloads a completed file.
4. `DELETE /api/mass-answer/jobs/{job_id}` cancels an active local task and removes its record/artifacts.
5. `POST /api/mass-answer/jobs/cleanup` removes expired, inactive records/artifacts.

Job metadata is persistent in PostgreSQL and artifacts live in a job-specific temporary directory. Work is executed by a tracked in-process task, not an untracked FastAPI `BackgroundTasks` callback. A client disconnect after HTTP 202 does not cancel it. There is no external durable queue: an application-process or host restart can interrupt work, queued/running jobs are not automatically resumed, and their last persisted status can remain stale until deletion or expiry cleanup. Completed results survive an application restart only while the host temporary filesystem remains intact.

Direct response files are deleted after the response lifecycle. Job files are retained until explicit deletion or expiry cleanup. A partial output is removed if serialization fails.

## Commands

Start the API in the project environment:

```bash
/root/miniconda3/envs/faq/bin/python3.12 -m uvicorn main:app --host 0.0.0.0 --port 7000
```

Submit the two-row direct fixture:

```bash
curl --fail-with-body -F 'file=@tests/fixtures/mass_answer/sample_persian.csv;type=text/csv' -F 'selected_docs=["General_FAQ"]' http://127.0.0.1:7000/api/mass-answer -o answered.csv
```

For a large upload, save the 202 JSON response, then:

```bash
curl --fail-with-body http://127.0.0.1:7000/api/mass-answer/jobs/JOB_ID
curl --fail-with-body http://127.0.0.1:7000/api/mass-answer/jobs/JOB_ID/result -o answered.xlsx
curl --fail-with-body -X POST http://127.0.0.1:7000/api/mass-answer/jobs/cleanup
```

These commands are state-changing only in the configured non-production application database/filesystem. Do not point them at production.
