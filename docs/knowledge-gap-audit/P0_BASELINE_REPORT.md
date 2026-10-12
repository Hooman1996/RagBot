# Knowledge coverage audit — P0 baseline

Status: **READY_FOR_REVIEW_WITH_BLOCKED_CHECKS**. Recorded 2026-10-12 (Asia/Tehran).
This report requests review; it does not authorize P1. No retrieval behavior,
prompts, defaults, routes, schema, KB records, vectors, or infrastructure changed.

## Repository and scope

- Actual checkout: `/root/projects/faq`, repository identified by the request as
  `Hooman1996/RagBot`. Remote URLs were not printed or needed for local work.
- Initial branch: `main`; actual HEAD and P0 base:
  `681cc9512fa585110e89586f13585290da639932`, identical to the reference.
- Stage branch: `p0/knowledge-coverage-baseline`, created at that HEAD in the
  existing worktree. A separate worktree was unnecessary: runtime files are
  unchanged and all stage files are new. No reset, stash, rebase, or merge.
- Existing tracked changes: `.gitignore` modified (21 added/3 removed lines);
  `.env.recommended.rtx5880-staging` deleted (55 lines). Preserved and excluded
  from the stage commit.
- Existing untracked paths, left untouched: `.env_latest`, `=5.4,`,
  `Deterministic_Giti_Prod_Commands.txt`, `General_FAQ.csv`,
  `Hooman_12_Month_Deep_AI_Systems_Robotics_Roadmap_2026.md`,
  `negah bank icon.png`, `previous-async-tei-proposal.txt`, `reponse_test.json`,
  `requirements_sep_8_2026.txt`, `skills-lock.json`. Their contents were not used
  as evaluation data or copied into deliverables.
- The user's ignore rule `/docs/*` excludes the requested directory. Only the
  three explicitly authorized documents are force-added; `.gitignore` stays
  untouched by P0.
- At inspection, no committed difference from the reference; only the preceding
  tracked changes differ in the worktree. No relevant retrieval/frontend source
  modifications were present.
- Applicable instructions: root `AGENTS.md`; no nested or ancestor AGENTS file
  found. Skills read at `.agents/skills/{debugging-strategies,
  python-testing-patterns,rag-implementation,design-taste-frontend,
  frontend-design}/SKILL.md`. Design-taste explicitly excludes dashboards/tables;
  only its scope/brief/preservation guidance applies. The managed-cloud runtime
  skill was also read; its environment-status tool is unavailable in this session.

The scoped commit comprises the three documents in this directory and
`scripts/knowledge_audit_p0_baseline.py`. Its hash is returned in the final report
and obtained with `git rev-parse HEAD`; embedding its own hash in this document
would create a circular commit dependency. No push, merge, or deploy.

## Current active application map

References below are function names and line anchors in the P0 base source,
not assumptions from old documentation.

| Step | Current source and behavior |
|---|---|
| Startup | `main.py:210` `lifespan`: constructs a non-stemming `PersianTextProcessor`, `DatabaseConnections.connect_all`, serialized Qdrant client, `DatabaseManager.init_db`, shared blocking runner, TEI sync/async HTTP clients, `AsyncOpenAI`, `RAGSystem`, history rewriter, factory classifier, `AgentService`, `AnsweringService`, mass-answer processor/job manager. **Do not run lifespan for a read-only audit**: DB initialization and bucket setup can write. |
| Browser/mobile ingress | `main.py:679` `query_documents`/`_query_documents` and `mobile_api.py` talk handling call shared `AnsweringService.answer`; normal chat paths persist conversations and are unsuitable for P0 diagnostics. |
| Preparation | `answering_service.py:158` `_answer`: original query → `text_processor.normalize` via blocking runner → `normalize_persian_text` → optional preceding history formatting/rewrite → normalize rewritten text → classify effective text → aliases for `general` only → validate selected datasources → graph execution. Original query is separately retained and injected into graph messages. |
| History | `conversation_history.py:230` `ProductionHistoryProvider.load_rewrite_messages`/`load_snapshot` read latest session `meta_data.agent_state`; `save_snapshot` writes state. `format_rewrite_history` uses the last up-to-six valid messages (three turns). `new_architecture/app/services/history/rewriting.py:86` `get_formatted_history_string` is a metadata fallback; `rewrite_query` calls `RAGSystem.generate_text`. These latest-state providers have **no historical cutoff** and cannot be used unchanged to replay old queries. |
| Classifier | `intent_classifier_factory.py:30,66` `load_intent_classifier_config`/`build_intent_classifier` validate artifact path, device, threshold, required flag and checksum. `intent_classifier.py:181` `_classify_detailed` normalizes, calls shared TEI query embedding, then checkpoint network; returns `general` or `chitchat`. This active classifier does not itself establish banking/KB scope or a personal-data exclusion. |
| Aliases | `utils/retrieval_query_canonicalizer.py:73` `canonicalize_retrieval_query`: ordered approved regex substitutions from `config/retrieval_query_aliases.json`, with artifact version/hash and enable setting. Classification precedes aliases. Canonical wording must not replace intended meaning in coverage judgments. |
| Graph | `agent_service.py:117` `_process_message` loads/hydrates provider state, sets original user input, retrieval query and preclassified intent, invokes graph and saves state subject to execution policy. `agent_graph.py:105` `make_classify_intent` consumes supplied intent instead of classifying again. Pending personal slots can route directly to `validate_slot`. `build_graph` registers the seven nodes documented in AGENTS. |
| Datasource/category | `DatabaseManager.filter_available_document_titles` (`database.py:734`) removes blank/duplicate/stale titles but retains requested order. `document_category.py:get_document_category` maps first title by text heuristics (`FAQ`, contract, announcement), falling back to a deterministic MD5-based choice; this is a prompt category, not authoritative taxonomy. `new_architecture/knowledge_sources.py:build_datasource_listing` supports listing. |
| PostgreSQL | `utils/rag_utils.py:107` `chunk_fetcher_factory` → `DatabaseManager.get_chunks_by_document_titles` (`database.py:755`) joins `chunks`/`documents`, filters title membership, returns chunk ID/text/document title; **no SQL ORDER BY**. Revision callback → `get_chunks_revision_by_document_titles`. Connections are per operation; a separate SQLAlchemy pool is not evidence that this path uses it. |
| Sparse search | `utils/persian_hybrid_search.py:550` `_get_or_build_bm25`: revision-aware process-local cache keyed by sorted allowed titles; `_build_temporary_bm25` tokenizes full stored chunks with legacy document overrides. Query processing disables those overrides. `_score_bm25` (`:742`) sorts score descending, string ID ascending, then takes 50; search drops nonpositive sparse hits. |
| Dense search | `_semantic_search` (`persian_hybrid_search.py:479`) → `_encode_query` → `TeiEmbeddingClient.embed_query`: normalized query, `prompt_name=query`, normalized vector; serialized Qdrant `query_points`, title payload filter, configured dense limit, chunk IDs only/no vectors. Dense ties sorted by score then string chunk ID. |
| Fusion | `PersianHybridSearch.search` (`persian_hybrid_search.py:590`) unions sparse/dense IDs and computes Python RRF with `k=60`. Sorts hybrid, dense, sparse scores descending then string ID; truncates to requested retrieval depth, rounds emitted scores to six decimals, preserves original RRF rank. Full answer chunks come from PostgreSQL. |
| Answer-context rerank | `RAGSystem.retrieve` (`utils/RagSystem.py:178`) delegates search. `agent_graph.py:137` `make_handle_general` reranks its results with `rerank_search_results` (`persian_hybrid_search.py:751`). `build_faq_rerank_text` (`utils/rag_utils.py:55`) intentionally uses question + category + subcategory; full answers remain on candidates. Unrecognized unstructured chunks fall back to normalized full content. |
| Context/generation | FAQ uses all selected reranker results; other prompt categories select first three. `RAGSystem.generate_context` (`utils/RagSystem.py:243`) serializes Q/A/taxonomy in ranked order with **local ordinal XML doc IDs**, which must be mapped to stable chunk IDs for audit evidence. `RAGSystem.answer` → `_completion` → OpenAI-compatible `chat.completions.create`; client model default `/app/model` is not proof of served model identity/context. |
| Related questions | `make_handle_general.prepare_context` takes titles/answers from the selected context, up to related-question depth. Separate `PersianHybridSearch.rerank` (`persian_hybrid_search.py:969`) scores question-only candidates, filters by graph threshold and returns up to five, graph then caps by configured related-question count. `main.py:_query_documents` and `mobile_api.py` return graph-related questions only for FAQ; neither reranks them again. `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD` is loaded but not used by this active path. This is not answer-context selection or coverage evaluation. |

Pipeline observers can carry raw query, history, chunks, prompts, and answers;
terminal debug can render content. The P0 helper never binds such an observer,
never loads runtime env, and does not evaluate content-emitting lazy factories.
Future audit workers must use a metadata allowlist, not serialize existing
observer payloads into operational logs. Private, authorized evidence storage
is distinct from logs.

## Known-issue observations (no repairs)

| Issue | Expected vs actual; evidence | Disposition |
|---|---|---|
| Missing rank 61 | A candidate absent from one ranked list contributes zero for that list. Actual `.get(cid, 61)` adds `1/121 = 0.008264462809917356`. Executed current search on two disjoint synthetic rank-1 hits returns `0.024658` each, rather than approximately `0.016393`; unrounded actual `0.024657905432868176`. | Confirmed defect; P1. |
| Fixed sparse depth | Wider retrieval should admit the configured sparse depth. Actual `_score_bm25` returns 50 of 120 positive synthetic scores irrespective of requested output depth. | Confirmed defect; P2. |
| One reranker request | Wider audit candidates must fit verified server limits through batching. Actual context method posts all texts once with `raw_scores=False`; 150 candidates become one request of 150. Synthetic server limit 50 rejects it. Current server compatibility is unknown. | Client limitation confirmed; actual live rejection unresolved; P3. |
| Index/scoring | Context reranker requires full list length, unique integer nonboolean indexes, finite nonboolean scores; maps original indexes and globally sorts score descending, RRF rank then ID. Related reranker is separate, accepts a list without requiring complete length, depends on server output order, and its integer check does not explicitly reject boolean indexes. | Preserve context guarantees in P3; test both paths. Probability scale and cross-batch comparability require live confirmation. |
| Taxonomy creation/edit | Payloads `ChunkCreatePayload`/`ChunkSyncPayload` have Q/A/is_qa, no category/subcategory. Clean Q/A reconstruct only those fields and omit taxonomy. `extract_qa_components` answer regex extends to end of content, so existing category text is embedded in editable answer: leaving that text intact accidentally preserves it. Synthetic source-derived reconstruction confirms both cases. | Conditional loss confirmed, not a claim that every edit drops taxonomy. P4 needs structured preservation. |
| Taxonomy revert | `api_revert_chunk` reads selected version content directly and passes it unchanged to `KnowledgeUpdateCoordinator.update`; coordinator updates PostgreSQL content/version, normalized embedding, Qdrant payload, and revision. | Direct stripping on revert **absent**. Reverting a version already missing taxonomy cannot reconstruct it; historical provenance remains unresolved. |
| Depth validation | `load_performance_settings` requires positive values, retrieval ≤ dense limit, context ≤ retrieval. Setting retrieval 150 alone against default dense 50 rejects; consistent 150/150/50 and 300/300/50 settings both accept. No hard ceiling at 50. Per-call search top_k does not expand global dense limit, and sparse remains fixed. | Coupled/global depth configuration confirmed; P2 should add isolated run depths while preserving production defaults. |

Do not add tests asserting these defects are desirable. P0 emits observations;
future regression tests assert corrected contracts and fail on current defects.
Additional risks for future acceptance: Qdrant IDs not in the fetched PG snapshot
can cause `chunk_dict[cid]` failure; SQL corpus ordering can vary; mixed datasource
category follows first title. Record these as uncertainty/scope errors, not gaps.

## Runtime capabilities and safety boundary

No current non-production service target was established. A local `.env` and
historical staging reports do not prove identity of the configured PG, Qdrant,
TEI, or vLLM target. No HTTP, database, Qdrant, normal chat, stress, or model call
was made. No service configuration/environment/container-environment dump.
`/etc/codex/network-policy.json` is absent and the managed environment-status
tool is unavailable; neither establishes staging readiness.

Local read-only resource discovery used `nvidia-smi --query-gpu=name,memory.total,
memory.used,utilization.gpu --format=csv,noheader,nounits` (exit **9**, no GPU rows)
and `docker ps --format '{{.Image}}'` after checking DOCKER_HOST was local/unset
(exit **1**, no inventory). These are unavailable observations, not GPU/server
measurements. The wrapper prints generic error codes, no raw configuration.

| Capability | Evidence available | Current verification |
|---|---|---|
| TEI reranker client batch | Historical `docs/configuration/RTX5880_MODEL_SERVER_BASELINE.md` reports 50. Current client performs one request; synthetic 50-limit fixture rejects 150. | Live limit blocked. |
| TEI length/truncation | Same historical report: embedding 16,384, reranker 8,192; auto_truncate true; TEI 1.9.3 and float16. | Documentation-only; not current. Pair/query accounting and truncation need tokenizer checks. |
| Model IDs | Historical embedding Jina v5 small retrieval / reranker BAAI bge-reranker-v2-m3; application sends `/app/model` to vLLM. | Served revisions/tokenizers unknown. |
| Rerank output | Source expects index/score rows; offline suite verifies index validation and deterministic context ordering. | Actual score transform/output order/cross-batch score comparability blocked. |
| vLLM context | Historical report explicitly says no running vLLM baseline; model-derived maximum is not an observed value. | Unknown; do not assume 4,000 or a model-card limit. |
| Concurrency/hardware | AGENTS describes staging RTX 5880 48 GB, production two L4 24 GB. Source defaults: admission 32, blocking 16, Qdrant 4, TEI/VLLM pools 32. | Application constants and topology documentation, not safe throughput. Start later diagnostics sequentially; audit capacity remains unproven. |

Later staging verification must establish the target and revision first, then
read allowlisted TEI `/info`, vLLM model/context metadata and tokenizer revision;
run only a few synthetic rerank pairs to verify response indexes, scores,
batch boundary and truncation. No service restart or model changes are needed
for baseline discovery. Do not infer production capacity from staging hardware.

## Executed baseline

Python interpreter: **3.14.6**. Available `httpx` and `dotenv`; missing pytest,
NumPy, psycopg2, qdrant-client, Parsivar, rank-bm25, Torch in this interpreter.
No dependencies installed. A canonical backend install lock was not established;
an untracked requirements file is not an approved dependency specification.

| Exact command | Exit / result |
|---|---|
| `python3 -m unittest tests.test_answer_context_reranking tests.test_performance_config tests.test_answering_service tests.test_history_aware_query_routing tests.test_knowledge_update_consistency tests.test_mass_answer_jobs tests.test_persian_normalization -q` | **0**, 57 tests in 0.782 s, OK. Synthetic/mocked component suite. |
| `python3 -m pytest tests/test_kb_audit_tools.py tests/test_step5_query_canonicalization.py tests/test_web_permissions.py -q` | **1**, pytest unavailable; tests did not collect/run. |
| `python3 -m unittest tests.test_kb_audit_tools -q` | **1**, import blocked on psycopg2; no audit-tool assertions ran. |
| `python3 scripts/audit_offline_frontend.py` | **0**, PASS, external runtime dependencies 0. |
| `node --test tests/analytics.frontend.test.cjs tests/kb_manager.frontend.test.cjs` | **0**, two test-file subtests passed, zero failures. No new audit UI exists to visually test. |
| `python3 scripts/knowledge_audit_p0_baseline.py` | **0** final execution; synthetic observations below. Initial helper development invocation exited 2 due to duplicate AST future imports; corrected before final run. |
| `python3 -m py_compile scripts/knowledge_audit_p0_baseline.py` | **0**, helper compiles. |
| `git diff --check` | **0**, existing tracked diff has no whitespace errors. |
| `git diff --cached --check` | **0**, four staged P0 deliverables have no whitespace errors. |

The helper extracts named current production methods by AST to avoid importing
service clients or loading `.env`. It executes search/rerank/reconstruction with
synthetic score providers, HTTP responses and immediate runner. Normalization,
tokenization, embedding, PG/Qdrant, generation and answer-context formatting
are not exercised by this fixture. It does not accept private datasets, contact
services, write reports, or assert defects correct. Exit 0 means execution
completed. Its JSON contains only fixture IDs, counts, code fingerprints,
settings outcomes and local timing.

Separate **source-default retrieval/context-ID mechanics baseline**:

- Sparse fixture: 120 positive scores → 50 sparse candidates. Dense request
  limits `[50,50]` across two repeated searches; fixture returns 50 overlapping
  dense IDs. Union 50 → final retrieval 10.
- Ordered final IDs `fixture-001` through `fixture-010`; repeated ordering equal.
- One answer-context reranker request of 10; fake response has reversed indexes
  and tied scores; selected IDs remain `fixture-001` through `fixture-010`.
  These are the IDs a FAQ graph would select at source defaults. Non-FAQ graph
  would slice three; full graph and generated answers were not run.
- Local fixture retrieval/repeat/rerank wall time **0.422 ms** in the recorded
  final helper run. Includes only synthetic callbacks; no service latency,
  throughput, GPU memory or answer-quality conclusion can be drawn.
- Separate audit-sized fixture posts 150 texts in one request and fails at a
  synthetic server limit of 50. This is not a claim about a live server response.
- RRF disjoint-list observations and configuration/taxonomy observations are
  recorded above. No production/audit comparison on real queries exists yet.

Code fingerprints emitted by the helper:

| File | SHA-256 |
|---|---|
| `utils/persian_hybrid_search.py` | `f77e018046c4e7a14a37b5c7a57818648f01958c7bbb9880a32ec0ef9f3df123` |
| `utils/performance_config.py` | `6aea4a79eac4f28257c7236b749f4a62e65fb2606e1adcbb42f7f5a48e6397fd` |
| `kb_manager.py` | `4ab4189e6d6d1cdd470df05016c2c9022550df4df59813e3b35ac32a8d5982ee` |

Existing `scripts/retrieval_stability.py:run_stability` was inspected. It makes
component retrieval/rerank calls without chat writes, records content/vector
hashes and ID/score order, applies normalization/aliases but **not history rewrite
or classification**, can default to all datasources, and reports no serving
latencies. It is useful after target verification, not a complete production
context/replay baseline. Existing exception handlers print exception strings:
do not archive raw stderr from private runs as content-safe operational logs.

`scripts/kb_signature.py:_postgres_signature` uses a named SELECT cursor in a
read-only PG transaction, rolls back/closes; `_qdrant_signature` scrolls points
and hashes payloads/vectors/collection configuration. `DatabaseManager.__init__`
does not initialize schema. Signature creation uses configured PG/Qdrant targets,
loads root `.env`, covers all chunks/collection, and has no non-production guard.
**Live creation skipped** until both targets are verified. Offline comparator
tests are dependency-blocked. Future commands (NOT executed):

```sh
python3 scripts/kb_signature.py create --label staging-frozen-p0 --output /tmp/kb-signature-before.json
python3 scripts/kb_signature.py compare /tmp/kb-signature-before.json /tmp/kb-signature-after.json
python3 scripts/retrieval_stability.py --query 'synthetic approved example' --runs 2 --document APPROVED_FIXTURE_SOURCE --retrieval-top-k 10 --rerank-top-k 10 --output /tmp/retrieval-baseline.json
```

A signature is a fingerprint, **not an immutable snapshot**. PG read-only
transaction plus paged Qdrant scroll do not give cross-store atomicity. Establish
a controlled immutable private export with PG Q/A/taxonomy/version/IDs, vectors,
payload mappings and collection configuration from an approved consistent
checkpoint; use repeatable-read PG extraction and owner-established matching
Qdrant checkpoint or verify no revision changes and matching before/after
signatures. Refuse inconsistent inputs. Keep content outside Git and operational
logs. Run every compared experiment against that frozen input; see plan.

## Env inventory (filenames and key names only)

No variables introduced, changed, or added to any env file in P0.

| File | Presence / tracked state / applicability |
|---|---|
| `.env` | Present, untracked/private; active root dotenv input. |
| `.env.server_git` | Absent, despite AGENTS claim; recheck each later stage. |
| `.env_latest` | Present, untracked/private; no active loader reference established. Preserve; determine intended runtime use before later settings propagation. |
| `env.example` | Present, tracked; main application template. |
| `.env.example.generated` | Present, tracked; generated template; generation workflow/applicability must be reconciled if later permanent keys are added. |
| `.env.recommended.rtx5880-staging` | Tracked in base but locally deleted by user; do not recreate during P0. |
| `evaluation_system/backend/.env`, `evaluation_system/deployment/.env`, `.env.local`, `.env.stage18` (under deployment) | Present, untracked/private; separate evaluation service, not new main-dashboard runtime. |
| `evaluation_system/backend/.env.example`, `evaluation_system/deployment/.env.example`, `evaluation_system/frontend/.env.example` | Present, tracked; separate service templates. No audit feature is routed there. |

Existing relevant key groups inventoried: `RAG_RETRIEVAL_TOP_K`,
`RAG_SEMANTIC_CANDIDATE_LIMIT`, `RAG_CONTEXT_RERANK_ENABLED`,
`RAG_CONTEXT_RERANK_TOP_K`, `RAG_QUERY_CANONICALIZATION_ENABLED`,
`RAG_RELATED_QUESTIONS_TOP_K`, `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD`,
`TEI_EMBED_URL`, `TEI_RERANK_URL`, `TEI_HTTP_*`, `VLLM_URL`, `VLLM_HTTP_*`,
`POSTGRES_*`, `QDRANT_*`, `INTENT_CLASSIFIER_*`, `WEB_*`, `RAG_PIPELINE_DEBUG*`,
`APPLICATION_REQUEST_TIMEOUT_SECONDS`, `REQUEST_*`. No values disclosed.
Generated template contains `TEI_EMBED_INSERT_BATCH_SIZE` and
`TEI_EMBED_MAX_CLIENT_BATCH_SIZE`; their presence does not configure reranking.

For each later permanent key: loader/default/validation + purpose/units + all
applicable tracked templates + every applicable existing private runtime file
(including `.env.server_git` if restored), preserving existing values. Report
filenames/key names only and commit no private files. No speculative P0 keys.

## Review blockers and P1 acceptance prerequisites

- Obtain current non-production identity/configuration and a supported dependency
  environment; confirm TEI limits/index behavior and vLLM model/tokenizer/context.
- Obtain approved evaluation queries and a frozen consistent KB input. Approximate
  1,800 FAQs is a project input estimate, not a measured P0 count. CSV feedback,
  failure flags and assistant answers are not required. A private CSV exists in
  the worktree but has not been approved/used as an evaluation fixture.
- Define session mapping, timestamp timezone policy, chronological assistant
  completion timestamps, taxonomy paths and FAQ-to-chunk identity mapping.
- Run P1 zero-contribution/missing-list/empty/tie tests; compare before/after
  retrieval IDs, selected contexts, call sizes and latency on the same fixtures,
  one variable only. Run labeled retrieval and answer-quality checks before
  accepting changed behavior. Mechanical P0 tests do not replace these.
- Review dashboard capability assignment and export/snapshot contracts before
  authorizing their implementation. No role grants or new page exist in P0.
