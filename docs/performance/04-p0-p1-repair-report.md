# P0/P1 compatibility repair report

Date: 2026-07-28

Base revision: `ad3da67` on `main`

External request deadline: 50 seconds

## Executive summary

This patch repairs the verified P0/P1 compatibility failures that were still
present on `main` after the TEI and async migration. The application source now
compiles, the active classifier uses the asynchronous TEI embedding callable,
LangGraph is compiled once and invoked asynchronously, all active AI callers
await their coroutine results, and successful vLLM answers can be cleaned and
returned.

The original user query is persisted and retained in agent history.
A rewritten query is carried separately as `retrieval_query` and is used only
for retrieval and final answer generation. Public request and success-response
schemas were not changed.

FAQ related-question reranking now calls TEI at `/rerank`, sends `query` plus a
list of candidate question strings, and maps every returned index back to the
complete question/answer candidate. It does not alter hybrid retrieval order or
the context used to generate the answer.

The final isolated unit suite passes 11 tests. Full `import main` validation
could not run in this checkout because the active Python interpreter does not
have `pandas` or the other application dependencies installed. No live TEI,
vLLM, Qdrant, PostgreSQL, MinIO, knowledge-base mutation, end-to-end, load,
retrieval-quality, or answer-quality request was run.

## Review inputs and evidence limitation

`docs/performance/02-tei-async-compatibility-review.md` was read and its P0/P1
findings were reproduced against `main`.

The requested file
`docs/performance/03-compatibility-test-results.md` does not exist in the
checkout, in the repository file inventory, or in any local Git revision
visible through `git log --all`. No findings have been inferred or invented for
that missing report. The patch scope is therefore based on report 02 plus
direct static reproduction on revision `ad3da67`.

Before the repair, `python3 -m compileall -q .` reproduced three syntax errors:

- `agent_graph.py:198`
- `intent_classifier.py:220`
- `new_architecture/app/services/history/rewriting.py:245`

The fourth syntax error recorded by report 02 in `utils/RagSystem.py` had
already been repaired in the merged base revision.

## Implemented verified P0/P1 repairs

| Severity | Verified failure | Repair | Evidence/tests |
|---|---|---|---|
| P0 | Three imported modules did not parse | Repaired chitchat await assignment, classifier async definition, and rewriting indentation | Full compile pass |
| P0 | `asyncio` was used without imports | Added imports in `main.py`, `agent_service.py`, and `utils/persian_hybrid_search.py` | Full compile and call-site scan |
| P0 | Startup referenced removed `search_engine.query_encoder` | Pass `search_engine._encode_query` as the classifier's async embedding callable | Static no-active-reference test |
| P0 | Classifier constructor, encoder, and callers had incompatible contracts | Removed active SentenceTransformer construction; made `classify`, `classify_detailed`, and `_encode` async; validate 1024 dimensions; await both active callers | Async classifier and graph tests |
| P0 | AgentService compiled an already compiled LangGraph | Keep `build_graph()` as the single compilation owner | AgentService fake compiled-graph test |
| P0 | Same-session replies could attach to the latest unrelated pending query | Carry the user row ID to assistant persistence and constrain the update by query, session, and user | Exact-query persistence test |
| P0 | Same-process concurrent turns could overwrite session state | Serialize `AgentService.process_message` by session | Concurrent same-session unit test |
| P1 | Successful vLLM answer cleanup raised `NameError` | Import `clean_llm_answer` in `utils/RagSystem.py` | Compile/static validation |
| P1 | Mobile classifier, rewrite, and graph calls were not awaited | Await all AI calls and offload its affected synchronous DB calls | Call-site/static tests |
| P1 | Mass-answer passed coroutine objects and an obsolete `alpha` argument | Await rewrite, retrieve, and answer; remove unsupported `alpha` | Call-site/static tests |
| P1 | History summary returned an unawaited coroutine | Make `summarize_history` async and await generation | Rewriting unit test |
| P1 | Related-question TEI reranking was disconnected and indexes were unmapped | Connect FAQ suggestions to `/rerank`, preserve returned order, reject invalid/duplicate indexes, and map to full candidates | TEI payload/mapping tests |
| P1 | KB create/update/revert referenced the removed local encoder | Use the TEI `/embed` contract from the existing synchronous FastAPI worker routes | Synchronous TEI payload/client-close test |
| P1 | Startup ignored partial data-service initialization | Abort lifespan startup when `connect_all()` returns false | Compile/static validation |
| P1 | No outer 50-second AI deadline | Wrap web query, mobile talk, and mass-answer implementations with `asyncio.wait_for(..., 50)` and return HTTP 504 on expiry | Static deadline tests |

## Original and rewritten query contract

The repaired state contract is:

1. `original_query` is the submitted query with surrounding whitespace removed.
2. `normalized_query` is used as the rewrite/retrieval input in the web flow.
3. The relational user query row stores the original value.
4. `AgentState.messages` stores the original value.
5. `AgentState.retrieval_query` stores the rewritten value, or the normalized
   value when rewriting is skipped.
6. Intent classification in LangGraph sees the original history message.
7. General retrieval and final answer generation use `retrieval_query`.
8. Chitchat continues to use the original message and performs no rewrite.

This changes no prompt text and no graph routing table.

## TEI compatibility behavior

Embedding requests use:

```json
{"inputs": "one string", "normalize": true}
```

at `${TEI_EMBED_URL}/embed`, and parse the first vector from the batch-shaped
response.

Reranking requests use:

```json
{"query": "one string", "texts": ["candidate zero", "candidate one"]}
```

at `${TEI_RERANK_URL}/rerank`. The application respects TEI's returned ordering
and maps `index` to the original complete candidate. The existing FAQ threshold
of `0.1` and top-five limit were preserved. Reranking affects only related
questions; answer context remains the original hybrid-search result set.

## Public API compatibility

The request models and successful response fields for `/api/query`,
`/api/mobile/v1/talk`, and `/api/mass-answer` are unchanged. The repair adds an
explicit HTTP 504 failure for the existing 50-second external deadline instead
of allowing an upstream timeout to terminate the request without an
application response.

## Tests added

`tests/test_p0_p1_repairs.py` contains 11 isolated standard-library tests:

- awaited graph classifier;
- awaited chitchat generation;
- original-query versus rewritten-query routing;
- FAQ reranker connection without answer-context changes;
- one graph compilation owner;
- same-session serialization;
- awaited rewrite and summary generation;
- exact query-row assistant persistence;
- TEI embed and rerank payloads;
- reranker index mapping and invalid-index rejection;
- synchronous KB TEI payload and deterministic client close;
- static async caller, deadline, SentenceTransformer, and `query_encoder`
  checks.

The tests use fakes at external-service/import boundaries and perform no
network, database, filesystem-data, or model inference.

## Validation commands and results

Run from `/root/projects/faq`.

| Command | Result |
|---|---|
| `python3 -m compileall -q .` before repair | Failed with the three syntax errors listed above |
| `python3 -m compileall -q .` after repair | Passed with no compilation errors |
| `python3 -m unittest -v tests.test_p0_p1_repairs` first harness run | 7 passed, 3 import-stub errors; the test boundary was corrected |
| `python3 -m unittest -v tests.test_p0_p1_repairs` second run | Passed, 10 tests |
| `python3 -m unittest discover -s tests -v` final verbose run | Passed, 11 tests; one pre-existing `datetime.utcnow()` deprecation warning |
| `python3 -m unittest discover -s tests -q` final quiet rerun | Passed, 11 tests |
| `git diff --check` | Passed |
| `python3 -c 'import main; assert main.app is not None'` | Could not run: `ModuleNotFoundError: pandas` |
| `command -v ruff`, `command -v mypy`, `command -v pytest` | All unavailable; no repository configuration for these tools was found |
| Async call-site `rg` scan | Every active classifier, rewrite, process, retrieve, and answer caller is awaited |
| Active local-encoder `rg`/AST scan | No active `SentenceTransformer` construction or `query_encoder` attribute reference on the application path; only comments and the inactive optional CrossEncoder facade remain |
| Minimal `asyncio.to_thread` smoke check in this audit interpreter | Did not complete within 5 seconds and was manually interrupted; unit tests therefore replace only the test copy of `to_thread` with a deterministic fake |

The final unit suite has zero failed tests. The application import check is a
blocked validation, not a pass.

## Static checks not available

No Ruff, mypy, pytest, pyright, tox, or repository-defined backend static-check
configuration is present in this checkout. Packages were not installed, in
accordance with the task constraints.

## Tests deliberately not run

- `python3 test_qdrant.py`, because its endpoint and credentials are not proven
  to target isolated staging.
- Live TEI/vLLM/Qdrant health or inference requests.
- Knowledge-base create/update/revert requests, because they mutate persistent
  data.
- PostgreSQL concurrency integration tests.
- End-to-end or load tests.
- Retrieval-quality and answer-quality tests, because no repository command or
  dataset exists.
- Frontend Vitest suites, which are unrelated to the repaired Python behavior
  and have missing local dependencies per report 02.

## Remaining P2 findings

These were intentionally not folded into the P0/P1 repair:

1. Shared HTTPX, AsyncOpenAI, Qdrant, and startup data-service clients are not
   all closed during lifespan shutdown.
2. TEI embedding responses used by retrieval and KB mutation are not fully
   validated for JSON type, finite numeric values, non-empty batch, and exact
   dimensions. The classifier does enforce its required 1024 dimensions.
3. Connect, read, write, and pool timeouts are not independently budgeted, and
   remaining deadline is not propagated to every downstream dependency.
4. TEI, vLLM, and Qdrant exceptions are not mapped to one stable banking error
   schema on every public route.
5. Several synchronous PostgreSQL, pandas, filesystem, Qdrant, and MinIO calls
   remain inside async routes or startup.
6. The per-session serialization lock is process-local. A multi-worker
   deployment still needs a database-backed concurrency strategy; worker count
   was not available for runtime confirmation.
7. The BM25 cache has no mutation invalidation or bounded concurrency policy.
8. Sensitive graph/debug prints remain on the request path.
9. TEI query-versus-passage task semantics and the classifier checkpoint's
   expected embedding adapter require retrieval/classification quality
   confirmation against the deployed services.
10. Non-FAQ prompt construction still receives `SearchResult` objects where a
    formatted string may be expected.
11. Startup and `/api/health` do not actively health-check TEI or vLLM.
12. History/session reads remain duplicated and several CPU transformations
    remain on the event loop.

No item above is claimed as a P0/P1 repair or a verified performance
improvement.

## Exact files and line ranges affected

| File | Affected lines after repair | Purpose |
|---|---|---|
| `agent_graph.py` | 23-40, 84-111, 115-179, 188-220 | Separate retrieval query, await classifier/answers, connect FAQ reranking |
| `agent_service.py` | 6-54, 79-150 | Import asyncio, single graph compile, session serialization, separate query values |
| `intent_classifier.py` | 20-28, 87-170, 181-285 | Remove local SentenceTransformer, async TEI embedding contract, dimension check |
| `main.py` | 1-70, 197-244, 383-510, 767-898 | Startup validation, async classifier wiring, deadlines, original query, exact query ID, batch awaits |
| `mobile_api.py` | 1-10, 73-186 | Deadline, DB offloads, awaited AI calls, exact query ID |
| `kb_manager.py` | 170-250, 253-337, 406-484 | Replace removed encoder in create/update/revert |
| `utils/RagSystem.py` | 17-20, 276-283 | Import answer cleanup helper |
| `utils/persian_hybrid_search.py` | 1-27, 204-263, 326-459 | Import asyncio, TEI embed adapter, rerank payload and index mapping |
| `new_architecture/app/services/history/rewriting.py` | 35-54, 244-251 | Await summary/rewrite generation and repair syntax |
| `new_architecture/app/services/history/database.py` | 447-496, 699-715 | Exact query-row assistant update |
| `tests/test_p0_p1_repairs.py` | 1-588 | Isolated regression suite |

## Proposed commit split

1. `fix: restore async TEI graph call chain`
   - Parse/import repairs, classifier contract, graph compilation, original and
     rewritten state, mobile/batch/summary awaits.
2. `fix: correlate query replies and enforce deadlines`
   - Exact query ID, same-session serialization, 50-second wrappers, startup
     failure propagation.
3. `fix: connect TEI reranking and KB embedding callers`
   - Related-question mapping and obsolete KB encoder removal.
4. `test: cover p0 p1 compatibility contracts`
   - Isolated unit and static contract suite.
5. `docs: record p0 p1 repair validation`
   - This report.

## Required end summary

### Files changed

- `agent_graph.py`
- `agent_service.py`
- `intent_classifier.py`
- `kb_manager.py`
- `main.py`
- `mobile_api.py`
- `new_architecture/app/services/history/database.py`
- `new_architecture/app/services/history/rewriting.py`
- `utils/RagSystem.py`
- `utils/persian_hybrid_search.py`
- `tests/__init__.py`
- `tests/test_p0_p1_repairs.py`
- `docs/performance/04-p0-p1-repair-report.md`

### Behavior changed

- The application parses; active AI coroutine chains are awaited.
- Classifier embeddings come from TEI and are checked for 1024 dimensions.
- Original and rewritten query values remain distinct.
- FAQ suggestions are reranked through TEI with correct candidate mapping.
- Assistant replies update the exact originating query.
- Same-process turns in one session are serialized.
- KB mutation routes use TEI rather than the removed local encoder.
- AI routes return HTTP 504 at the 50-second deadline.
- Partial startup connection failure aborts startup.

### Tests added

11 isolated compatibility tests in `tests/test_p0_p1_repairs.py`.

### Tests passed

11 of 11 in the final unit run; full Python syntax compilation and diff checks
also passed.

### Tests failed

0 in the final unit suite. Full application import remains blocked by missing
`pandas`; Ruff, mypy, and pytest are unavailable.

### Remaining P2 findings

Client shutdown, full dependency timeout budgeting/error mapping, embedding
response validation, cross-process session concurrency, blocking I/O, cache
coherency, sensitive logging, live service health checks, and embedding-task
quality confirmation remain for later scoped batches.

### Rollback instructions

Preferred after committing this batch:

```bash
git revert <p0-p1-repair-commit-sha>
```

Before committing, preserve and reverse only this reviewed patch:

```bash
git diff --binary > /tmp/faq-p0-p1-repair.patch
git apply --check -R /tmp/faq-p0-p1-repair.patch
git apply -R /tmp/faq-p0-p1-repair.patch
```

Review `git status --short` before applying either rollback method so unrelated
work is not included.
