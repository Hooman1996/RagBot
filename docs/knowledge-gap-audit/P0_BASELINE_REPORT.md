# Knowledge coverage audit — P0 baseline

Status: **READY_FOR_REVIEW_WITH_BLOCKED_CHECKS**. Recorded 2026-10-12 (Asia/Tehran).
This report requests review; it does not authorize P1. No retrieval behavior,
prompts, defaults, routes, schema, KB records, vectors, or infrastructure changed.

## P0.1 follow-up — current evidence

Completed on the existing `p0/knowledge-coverage-baseline` branch, starting at
P0 commit `3a9f9a4d05198686ac7b85cfe8370c01a3820825`. This follow-up changes only
this report. All unrelated changes present at the start were preserved. No env
keys/files, diagnostic code, dependencies or runtime behavior were changed.
The sections below this follow-up retain the **initial P0 evidence**; the
interpreter, effective-settings and live-capability findings here supersede its
missing-dependency and unverified-target blockers. P1 has not begun.

### Interpreter and checks

Shell activation worked. Every Python command below ran from
`/root/projects/faq` after this prefix:

```sh
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

`python -c 'import sys; print(sys.executable); print(sys.version.split()[0])'`
exited **0**, selecting `/root/miniconda3/envs/faq/bin/python`, **Python 3.12.12**.
`conda run` fallback was unnecessary. The initial P0 interpreter was base Python
3.14.6; missing packages there did not describe the confirmed `faq` environment.

| Executed command | Exit / result |
|---|---|
| `python -m pytest tests/test_kb_audit_tools.py tests/test_step5_query_canonicalization.py tests/test_web_permissions.py -q` | **0** outside the sandbox: **43 passed, 9 subtests passed**, 23 warnings, 15.22 s. The first sandbox execution stalled after 20 progress markers and was interrupted with Ctrl-C, exit **130**; it was not counted as a passing suite. |
| `python -m unittest tests.test_kb_audit_tools -q` | **0**, **7 tests** in 0.005 s, OK. Signature/comparator/stability primitives use synthetic records; no service calls. |
| `python scripts/knowledge_audit_p0_baseline.py` | **0**. Same source fingerprints and defect observations as initial P0; source-default fixture time **0.481 ms**. It deliberately does not load `.env`: this remains the 10-retrieval/50-dense/10-context source-default fixture, not the effective deployment configuration. |
| `python -m unittest tests.test_answer_context_reranking tests.test_performance_config tests.test_answering_service tests.test_history_aware_query_routing tests.test_knowledge_update_consistency tests.test_mass_answer_jobs tests.test_persian_normalization -q` | **0**, **57 tests** in 0.889 s, OK. |
| `python scripts/audit_offline_frontend.py` | **0**, PASS; zero external runtime dependencies. |
| `node --test tests/analytics.frontend.test.cjs tests/kb_manager.frontend.test.cjs` | **0**, both test-file subtests passed; zero failures. |

Pytest warnings concern SWIG types, unavailable NVML initialization and the
existing deprecated `TemplateResponse` parameter order. They are recorded, not
repaired in this baseline-only stage. The completed pytest run used existing
isolated ASGI fixtures, replacing lifespan/service operations; it did not start
the application, initialize schema, or persist test conversations.

### Effective retrieval configuration

Read `/root/projects/faq/.env` using the existing dotenv configuration policy:
`load_dotenv(Path('/root/projects/faq/.env'), override=False)` **before** importing
`utils.performance_config.PERFORMANCE_SETTINGS`. This matches the repository's
explicit-root audit loader and environment-precedence semantics. Load returned
true; none of the following keys was inherited before loading, so no shell
override affected these results. No env contents, endpoint URLs, credential
values, headers, or whole settings objects were printed or saved.

| Non-secret effective key | Value |
|---|---:|
| `RAG_RETRIEVAL_TOP_K` | 50 |
| `RAG_SEMANTIC_CANDIDATE_LIMIT` | 50 |
| `RAG_CONTEXT_RERANK_ENABLED` | true |
| `RAG_CONTEXT_RERANK_TOP_K` | 10 |
| `RAG_QUERY_CANONICALIZATION_ENABLED` | true |
| `RAG_RELATED_QUESTIONS_TOP_K` | 3 |
| `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD` | 0.1 |
| `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD` | 0.5 |

The mobile threshold is loaded but unused by the current graph/response path,
as established in the architecture map. The effective retrieval request is 50
candidates, context rerank selects up to 10 (FAQ) or three (other prompt category).
This is **configuration evidence**, not a measured real-query retrieval result.
The fixed BM25 slice remains 50 and the RRF defect remains unchanged.

Reproduction recipe for this settings-only observation (no live requests):

```sh
python - <<'PY'
import os, json
from pathlib import Path
from dotenv import load_dotenv
keys = (
    'RAG_RETRIEVAL_TOP_K', 'RAG_SEMANTIC_CANDIDATE_LIMIT',
    'RAG_CONTEXT_RERANK_ENABLED', 'RAG_CONTEXT_RERANK_TOP_K',
    'RAG_QUERY_CANONICALIZATION_ENABLED', 'RAG_RELATED_QUESTIONS_TOP_K',
    'RAG_RELATED_QUESTIONS_RERANK_THRESHOLD',
    'MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD',
)
inherited = set(os.environ)
loaded = load_dotenv(Path('/root/projects/faq/.env'), override=False)
from utils.performance_config import PERFORMANCE_SETTINGS
print(json.dumps({
    'dotenv_loaded': loaded,
    'effective_retrieval_settings': {
        k: getattr(PERFORMANCE_SETTINGS, k.lower()) for k in keys
    },
    'inherited_override_keys': [k for k in keys if k in inherited],
}, sort_keys=True))
PY
```

### Confirmed development/staging checks

The user explicitly confirmed **all** configured `TEI_EMBED_URL`,
`TEI_RERANK_URL`, `VLLM_URL`, `POSTGRES_HOST` and `QDRANT_HOST` targets are
development/staging. Configuration classification showed all are loopback;
values were not printed. This removes the initial target-identity blocker.
The managed environment-status tool and network-policy file remain unavailable.

Initial sandbox HTTP/Qdrant probes failed with socket permission errors;
PostgreSQL also failed there. These were not serving-limit observations.
Bounded approved probes were then rerun with sandbox escalation: no proxy
settings were removed, no redirects followed, and no credential/configuration
dumps were made. Escalation also resolved the stalled offline ASGI test suite.

Executed capability probes were activated `python -` stdin programs using
`httpx.Client`, `psycopg2`, `QdrantClient` and filtered local Docker metadata.
Their successful program exits were **0**; individual HTTP/CLI outcomes appear
below. HTTP metadata timeouts were three seconds, rerank timeouts ten seconds,
PG connect timeout three seconds, Qdrant timeout three seconds, local CLI timeout
five seconds. No chat endpoints, answer generation, stress sweep, model loading,
service restart, schema change, KB edit or vector write was performed.

| Executed operation | Current result |
|---|---|
| GET configured `TEI_EMBED_URL` + `/info` | **200**; TEI **1.9.3**, model `/app/models/models--jinaai--jina-embeddings-v5-text-small-retrieval`, last-token pooling, max client batch **64**, max input length **32,768**, automatic truncation **false**, max batch tokens **32,768**, max batch requests **32**, max concurrent requests **100**. |
| GET configured `TEI_RERANK_URL` + `/info` | **200**; TEI **1.9.3**, model `/app/models/BAAI--bge-reranker-v2-m3`, reranker type, max client batch **64**, max input length **8,192**, automatic truncation **false**, max batch tokens **32,768**, max batch requests **32**, max concurrent requests **100**. |
| GET configured `VLLM_URL` + `/models` | **200**; served ID `/app/model`, advertised `max_model_len` **8,192**. |
| GET vLLM origin + `/version` | **200**, version **0.26.0**. |
| GET vLLM origin + `/tokenizer_info` | **404**; no runtime tokenizer-object information established through that endpoint. |
| Three POSTs to TEI `/rerank` | Each **200**, three synthetic texts per request; `raw_scores=False`, repeated `False`, then `True`. All returned all three unique input indexes, descending score order and order `[0,2,1]`. Wall times **55.603 / 18.339 / 30.420 ms**; tiny sequential diagnostics, not throughput or production latency benchmarks. |
| One POST to TEI `/rerank` with 65 short synthetic texts | **422**, **7.776 ms**, above reported batch limit 64. Response body not logged. This verifies rejection at 65; acceptance exactly at 64 was not tested. |
| PostgreSQL connection, read-only transaction, `SELECT 1` | Succeeded; rollback and close. No DDL/DML or customer-query reads. |
| Qdrant `get_collection` | Succeeded; **1,526 points**, green collection status. Collection name and credential values omitted. |
| `nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits` | Sandbox exit **9**, escalated exit **18**, no usable GPU rows. GPU memory/utilization/capacity remains unverified. |
| Local `docker ps --format '{{.ID}}'`, after checking Docker daemon selector was local/unset | Sandbox inventory exit **1**; escalated exit **0**, nine running containers. Only inference command flags and model-mount configuration/tokenizer fingerprints were subsequently selected; no container environments/full configuration printed. |

Reranker fixtures were query `alpha fixture` and texts `alpha fixture`,
`beta fixture`, `gamma fixture`. Only response indexes/scores were inspected;
no text-return option was requested. Repeated scores were **not exactly equal**:
maximum difference **0.00033257**, while ID order was unchanged. False-mode scores
were within [0,1]; true-mode scores included negative and positive logits. This
does not establish calibrated probabilities or an exact score transform across
separate executions. Cause and cross-batch score comparability remain unverified;
future batching acceptance must not assume bitwise score reproducibility.

Allowlisted launch flags corroborated both TEI services' float16 dtype,
batch/concurrency settings and `--auto-truncate false`. vLLM flags corroborated
`--max-model-len 8192`, bfloat16, `--max-num-seqs 64`,
`--max-num-batched-tokens 8192`, and `--gpu-memory-utilization 0.75`.
These are observed serving controls, **not proven safe audit concurrency or
usable GPU headroom**. No oversized-token request was sent: input limits and
truncation policy are metadata/launch-flag verified, not boundary-token tested.
Production default 50 rerank candidates fit the current 64-item client limit;
the proposed 150-item unbatched audit request still exceeds it.

Mounted model artifacts were read without executing model code or printing
chat templates/full JSON. Tokenizer configs identify GemmaTokenizer (vLLM),
XLMRobertaTokenizer (reranker) and Qwen2Tokenizer (embedding); model configs
identify Gemma4UnifiedForConditionalGeneration, XLMRobertaForSequenceClassification
and Qwen3Model respectively. No immutable upstream model/weight revision was
established. These are mounted-artifact identities, not proof of the exact
in-memory tokenizer implementation. Fingerprints:

| Service / artifact | SHA-256 |
|---|---|
| vLLM `config.json` | `e75e44bd91f24d077e83404c02b69a6e6d844b54b27ec929724d05f410258536` |
| vLLM `tokenizer_config.json` | `09e6222fd7049dae603d0f61a8b10af5a813f22dca10e6cdc6918f76d7661104` |
| Reranker `config.json` | `13dcd6c31d9fec9d1d8e158702072f62d7fa7d312a64b9fe057bec9a08cfe41a` |
| Reranker `tokenizer_config.json` | `7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4` |
| Reranker `tokenizer.json` | `69564b696052886ed0ac63fa393e928384e0f8caada38c1f4864a9bfbf379c15` |
| Embedding `config.json` | `f59f2ca97a4c6bdaa97722d1f8a93ff8823612a4ccba94e0af1f338d226aec56` |
| Embedding `tokenizer_config.json` | `1cc816812993bff176eb4f7495433b736f06fba9b6e7b05cac7b4a1780650c95` |
| Embedding `tokenizer.json` | `be75606093db2094d7cd20f3c2f385c212750648bd6ea4fb2bf507a6a4c55506` |

### Read-only KB fingerprint

Reused `scripts.kb_signature.create_signature` after target confirmation and
successful read-only PG/Qdrant connectivity. It uses the script's root `.env`
loader and existing read-only/hash behavior. An activated Python stdin wrapper
called `create_signature('dev-staging-p01')`, then `write_json_report` to
`/tmp/ragbot-p01-kb-signature.json`, printing only counts/hashes and safe error
types. Wrapper exit **0**; no exception or raw KB record was printed. The Qdrant
SDK emitted its generic insecure-connection API-key warning, without key values.
No configuration was changed in response.

- PostgreSQL records **1,526**; Qdrant points **1,526**.
- Cross-store consistent **true**; zero PG-only/Qdrant-only, duplicate logical
  ID, missing vector, wrong dimension, content mismatch and metadata mismatch
  counts. This is the tool's current consistency finding, not an immutable or
  cross-store atomic snapshot guarantee.
- PostgreSQL aggregate:
  `948cae670aaec5faa350d977a0f381d6410a9b48d7853cdfd18bff7c76310750`.
- Qdrant logical aggregate:
  `1662fdbff79f96982d77dd45633b504c7abc4730b12de17563beddff8bee9343`.
- Qdrant vector aggregate:
  `047ced69c2c6beb50ab709aaa17b60472f3b3d71b2e9b6120185a729cae58b93`.
- Collection configuration fingerprint:
  `b3bc80fa69ee848cf02a3dabe11b67d9500b4b125f63a055608fcf109a7f06f3`.
- Local signature artifact fingerprint:
  `78d03e65f156eae2a06d54afdba0a94f0609cc3a77f8d226977c4323d46477cd`.

The signature stays outside Git; no KB content, private CSV, prompt, raw model
response, runtime env or credential is committed. The measured count is chunks/
points, not a verified count of distinct FAQs. No controlled frozen Q/A/vector
snapshot or real-query baseline was established in P0.1.

### P1 readiness and remaining acceptance prerequisites

**P0.1 is ready for review with remaining acceptance blockers.** Correct interpreter,
offline test execution, configured target identity, current service limits,
rerank index behavior and signature-tool execution are now established. The
RRF defect has a reproducible mechanical baseline and a focused implementation
contract; P1 remains awaiting explicit authorization, not automatically approved.

P1 behavior-change acceptance still requires an approved consistent frozen
evaluation input, labeled retrieval tests and answer-quality tests, and paired
before/after retrieval/context/call-size/latency measurements with only RRF changed.
No real-query answer-quality score or throughput claim can be made from these
checks. GPU telemetry is unavailable; exact serving tokenizer/weight revisions,
token-boundary behavior and cross-batch score comparability remain unresolved
for later budgeting/batching/capacity work. Session/timestamp replay assumptions
remain audit-stage prerequisites. No previous code defects were repaired.

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

## Initial P0 runtime capabilities and safety boundary

During initial P0, no non-production service target was established. A local `.env` and
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

## Initial P0 executed baseline

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

## Initial P0 review blockers and P1 acceptance prerequisites

Target identity, supported interpreter, offline execution and live service-limit
discovery below are now resolved by P0.1. Its readiness subsection above is the
current blocker list; the following preserves the initial P0 review record.

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
