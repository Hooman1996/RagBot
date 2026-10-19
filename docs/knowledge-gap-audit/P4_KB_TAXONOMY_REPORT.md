# P4 — FAQ taxonomy preservation

Status: **READY_FOR_REVIEW_WITH_BLOCKED_CHECKS**. P4 is complete for review;
isolated live write transactions and browser visual verification remain blocked.
No acceptance gate, audit implementation, push, merge, deployment, or restart
was begun. The main-dashboard, explainability, all-query processing, and complete
per-input-row CSV contracts in the implementation plan remain unchanged.

## Repository and environment

Project `/root/projects/faq`; branch `p4/kb-taxonomy-preservation`, base
`e15761f5eb8d173ad6ebbe0ac9f02aba70503dcf` (actual initial HEAD matched P3).
No reset, rebase, merge, stash, or worktree relocation was needed.
Pre-existing `.gitignore` modifications, deleted
`.env.recommended.rtx5880-staging`, private `.env_latest`, and unrelated
untracked files were preserved and excluded from the P4 commit.
Use `git log -1` for the resulting scoped commit; this report is in that commit.

Commands below used:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

Interpreter `/root/miniconda3/envs/faq/bin/python`, Python **3.12.12**.
The existing diagnostic loader explicitly loads `/root/projects/faq/.env`
with `load_dotenv(..., override=False)`; no private configuration is copied.
Effective non-secret settings are unchanged:

| Setting | Effective value |
|---|---:|
| RAG_RETRIEVAL_TOP_K | 50 |
| RAG_BM25_CANDIDATE_LIMIT | 50 |
| RAG_SEMANTIC_CANDIDATE_LIMIT | 50 |
| RAG_CONTEXT_RERANK_ENABLED | true |
| RAG_CONTEXT_RERANK_TOP_K | 10 |
| TEI_RERANK_MAX_CLIENT_BATCH_SIZE | 50 |

Live capability responses matched the frozen P3 identity: reranker server
client limit 64, input limit 8192, automatic truncation disabled, and vLLM
context limit 8192. The client setting remains 50; no server flags changed.
**New environment variables: none. Env files changed in P4: none.**

## Actual loss conditions and representation

`kb_manager.py:ChunkCreatePayload`, `ChunkSyncPayload`, `api_create_chunk`, and
`api_sync_chunk` previously reconstructed clean FAQ submissions as question and
answer alone. They did not have explicit taxonomy fields. Clean answer edits
therefore lost the current footer. Conversely, the old
`extract_qa_components` could leave the footer inside the answer, allowing some
legacy edits to preserve it accidentally. Revert itself already used exact
stored version content; an uncategorized historical version cannot recover
taxonomy from nothing.

Taxonomy remains in existing structured chunk content, using
`question category:` and `sub_category:`. PostgreSQL chunks and version content
are authoritative; Qdrant `content` and `text` receive the same full text.
`utils/rag_utils.py:parse_faq_relevance_fields` and `build_faq_rerank_text` read
question/category/subcategory for reranking; answer-aware scoring is not added.
BM25 sees full chunk text, stored-document embedding sees the existing Parsivar
normalized full text, and `utils/RagSystem.py:generate_context` receives full
answers and taxonomy. These retrieval/context implementations remain unchanged.

## Parse/compose and payload contract

`utils/faq_content.py` provides shared `parse_faq_content`,
`split_taxonomy_suffix`, and `compose_faq`. `extract_qa_components`, creation,
update preparation, and read/version responses use that contract.

Canonical JSON names are `main_category` and `sub_category`, matching current
retrieval conventions. Accepted aliases are `category` and `subcategory`.
Contradictory canonical/alias values reject with 422. Labels must be strings or
null, be single-line, and contain no embedded metadata markers. Existing label
separator cleanup is reused. No title-based taxonomy inference occurs.

| Input | Creation | FAQ update |
|---|---|---|
| Field omitted | Use recognized unique legacy footer, otherwise uncategorized | Preserve the locked current field |
| Explicit null or empty/whitespace label | Clear that field | Clear that field |
| Explicit nonempty label | Override a unique legacy value | Apply and version the change |
| Parent changed, child omitted | Do not transfer a legacy child to a different parent | Clear the child |
| Parent explicitly cleared, child omitted | No child | Clear the child |
| Child explicitly supplied without a parent | Reject 422 | Reject 422 |

Parent-only and fully uncategorized FAQs remain valid. An existing legacy orphan
child is retained on an answer-only update without inventing a parent; explicitly
editing it requires a consistent path. Raw/non-FAQ content is not composed or
given taxonomy, and its text remains unchanged apart from existing submission
trim/embedding normalization behavior.

Only a dedicated terminal metadata block is interpreted as a footer. Inline,
quoted, and closed fenced answer prose is retained. Repeated identical metadata
collapses on composition; conflicting duplicates reject even if explicit fields
are supplied. Reads preserve ambiguous source text and expose a generic
`taxonomy_error`; they do not pick a category or erase answer facts.

For creation, explicit fields take precedence over a unique legacy footer.
For updates, an omitted legacy footer field must match the current record;
different embedded taxonomy rejects with a safe 422 message asking the client to
refresh or use explicit fields. This prevents an old embedded footer from
restoring taxonomy that was concurrently changed or cleared. Legacy clients
that submit matching footers or omit metadata continue working; clients wishing
to change taxonomy must send explicit fields. Same-line legacy Q/A and singleton
wrappers remain readable. Numbered answer sections are retained inside one
canonical outer `answer:` field so the existing generation parser keeps every
section. A semantic no-op keeps the original bytes rather than reformatting them.

## Coordination, consistency, no-op, and revert

`new_architecture/knowledge_update.py:KnowledgeUpdateCoordinator.update` accepts
an internal preparation callback for FAQ updates. It prepares against preflight
content for embedding, then re-resolves omissions against the row held by the
existing `PsycopgKnowledgeRepository.lock` (`FOR UPDATE OF c,e`). If a concurrent
change alters the composed content, it embeds the final content while locked.
Explicit changes remain deliberate last-writer updates; this is not a new
optimistic concurrency protocol for answer edits.

Changed content follows the existing staged chunk/embedding/version/document
revision transaction, Qdrant upsert/read-after-write verification, PostgreSQL
commit/fresh verification, and local cache invalidation. Embedding model/dimension
lineage fields are preserved. Document revision increments keep another worker's
revision-aware corpus cache fresh. No schema or bulk migration was added.

Old unchanged-content operations skipped embedding but still wrote vectors,
versions, revisions and cache invalidations. A genuine no-op now verifies current
content plus Qdrant text/content/vector and canonical source mapping while locked,
releases the transaction, and returns `no_op=true` with no writes or invalidation.
Missing or inconsistent derived state still follows the repair pipeline. The
success response includes clean fields from the actual merged content so the
editor can refresh concurrent taxonomy correctly. Content is excluded from the
coordinator's operational result serialization/logging.

Existing rollback, lost-commit outcome checks and Qdrant compensation are retained.
Content validation rejects before storage writes. If rollback itself fails,
`repair_required=true` is reported and unsafe vector restoration is avoided.
Synthetic tests cover embedding failure, vector confirmation failure, failed
compensation, lost commit/unknown commit outcomes, cache failures and concurrent
metadata change/clear. This remains the existing compensating consistency model,
not an atomic cross-store transaction.

`kb_manager.py:api_revert_chunk` still passes the selected stored version literally
through the coordinator. Categorized and uncategorized versions restore their
own content, vectors, versions and caches; today's taxonomy is never injected.
Historical versions were not rewritten or backfilled.

## Existing editor

The existing KB editor adds optional labeled category/subcategory controls in
create and FAQ edit forms. GET responses supply clean question/answer fields and
taxonomy separately. Answer-only requests omit unchanged metadata; changed
values are explicit, and clearing sends null. Changing a parent clears the child
control. Blank creation controls omit metadata so a pasted legacy footer survives.
Subcategory/parent validation focuses the relevant control, ambiguity blocks save,
and successful merged/no-op responses refresh the displayed fields.

History shows that version's taxonomy or its absence. Existing escaping is used
for labels/history, controls use `dir=auto`, visible focus, native labels and a
mobile one-column layout. The existing local fonts/assets, palette, navigation,
authentication, permission middleware and CSRF fetch wrapper are retained.
No new CDN, framework, role, route or dashboard redesign was introduced.

## Executed checks

All final commands below exited **0**. Counts overlap; they are not added together.

```bash
python -m pytest tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py tests/test_kb_manager_chunk_create.py tests/test_kb_manager_database_config.py tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py tests/test_kb_phrase_normalization.py tests/test_web_permissions.py tests/test_web_auth.py tests/test_rrf_scoring.py tests/test_retrieval_depths.py tests/test_reranker_batching.py tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py tests/test_answer_context_reranking.py tests/test_rag_answer_prompt_roles.py tests/test_performance_config.py tests/test_validate_environment.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py tests/test_kb_audit_tools.py -q
node tests/kb_manager.frontend.test.cjs
python scripts/audit_offline_frontend.py
python scripts/knowledge_audit_p0_baseline.py
git diff --check
```

The final backend selection passed **248 tests and 203 subtests** in **18.34
seconds**. The prior selection, before adding the same-line legacy test, passed
247 tests and 203 subtests in 17.58 seconds. The focused storage/API/cache run passed **57 tests
and 22 subtests** in 13.41 seconds. Existing warnings concern SWIG, local NVML,
`datetime.utcnow` and Starlette template calling conventions.

Frontend VM tests: **6 passed**, covering read-only controls, escaped full content,
taxonomy prefilling, answer-only omission, merged response refresh, parent clear,
validation focus, creation/legacy/raw payloads, and ambiguity blocking. HTTP tests
exercise real middleware: existing editor/admin writes allowed, viewer/user denied,
and missing CSRF denied. The offline asset audit passes with **0 external runtime
dependencies**. These are functional/static checks, not actual browser visuals.
No local Playwright/Puppeteer/browser executable is available; rendered visual,
keyboard traversal and responsive screenshot checks remain unperformed.

The updated P0 diagnostic is offline, synthetic, and does not load env files:
taxonomy preserved in explicit creation, omitted-field edit and legacy metadata;
RRF corrected, BM25 depth configurable, 150 candidates safely reranked 50/50/50,
and revert still uses literal stored content.

During development, two fixture errors were corrected: mutation of a frozen
VectorPoint and an assertion ignoring existing Parsivar punctuation normalization.
The initial focused run had 2 failures/39 passes/22 subtests; subsequent focused
and full checks passed. No live write was performed to diagnose these failures.

## Frozen comparisons and measurements

Private material is restricted to `/tmp/ragbot-p4-taxonomy-20261013` (0700;
files 0600). No KB content, queries, prompts or responses were committed. The
helper uses in-memory write stores and explicit staging confirmation for live
component calls. It rejects configuration or frozen-input drift.

Identifiers:

- Frozen P3 first-stage input: `9926d2dc6499c99ee14ccfe56306dbfef4b9cda4b262cff634dab999f3a8335f`.
- Effective retrieval/model configuration: `c8af233fbe4b854dd5beedd18a3b2efeee5278a0a3f566c02db3681798ea2d65`.
- Unchanged retrieval source: `11e4d58c683ed6cc9d8899edf44c807088d0c70324b0838137d6e78657ebf1ce`.
- Paired complete-store synthetic write fixture: `dd764604ab5aeacb334bb8a634f424ec47adf42b15c3ad349820cdf208388e79`.
- Newly composed two-FAQ synthetic fixture: `5c43f3b829be4f8f9baa9da6dc26242ffb536c7555e8de0e9c20824df882137e`.

Exact comparison commands (each exit 0):

```bash
python scripts/kb_taxonomy_p4_compare.py before --directory /tmp/ragbot-p4-taxonomy-20261013 --confirmed-staging
python scripts/kb_taxonomy_p4_compare.py paired --directory /tmp/ragbot-p4-taxonomy-20261013
python scripts/kb_taxonomy_p4_compare.py after --directory /tmp/ragbot-p4-taxonomy-20261013 --confirmed-staging
python scripts/kb_taxonomy_p4_compare.py inventory --directory /tmp/ragbot-p4-taxonomy-20261013 --confirmed-staging
python scripts/kb_taxonomy_p4_compare.py composed --directory /tmp/ragbot-p4-taxonomy-20261013 --confirmed-staging
```

The initial before fixture had minimal point metadata. For the primary paired
write comparison, both checkpoint and current code use the same complete
canonical store fixture, alternating execution order, 100 operations per side
per case. The checkpoint coordinator/API are extracted from P3 and used only
with mocks. This avoids comparing different metadata representations. Initial
before/standalone after artifacts are retained, but are not treated as that pair.

| Mocked operation | P3 median / p95 ms | P4 median / p95 ms | P3 → P4 calls: embedding/vector/version/cache |
|---|---:|---:|---|
| Answer-only edit | 0.652 / 0.894 | 1.185 / 1.544 | 1/1/1/1 → 1/1/1/1 |
| Taxonomy-only edit | 0.618 / 0.922 | 1.130 / 1.201 | 1/1/1/1 → 1/1/1/1 |
| Clean unchanged submission | 0.619 / 0.673 | 0.959 / 1.242 | 1/1/1/1 → 0/0/0/0 |
| Matching legacy unchanged submission | 0.684 / 0.724 | 0.973 / 1.011 | 0/1/1/1 → 0/0/0/0 |

P3 lost taxonomy on the first three cases; P4 retained/applied it. All predefined
answer facts survived. Changed operations have equal stored content and vectors
across mock PG/Qdrant and a complete new version. The small local overhead reflects
parsing/preparation and consistency checks; these timings are **not service or
database latency**. In a deliberately raced answer edit, re-embedding the locked
merged content required two embedding calls rather than one; this is necessary
to preserve the concurrent taxonomy and vector association.

Frozen first-stage replay: three labeled synthetic questions and two approved KB
title queries, each 50 results; **all five ordered IDs and full contents match P3**.
Unmodified source/config hashes also match. Before/after staging operations are
sequential at logical concurrency one: 10 answer-context rerank calls plus 5
related-question calls per side, all requests of 50. Selected relevant-entry
coverage is **8/8** both sides, synthetic context facts **9/9**, and three real
vLLM answers pass **9/9** predefined lexical fact/condition checks, with zero
forbidden claims. No natural customer conversations were used or persisted.

Selected sets match in all five cases; one synthetic case changes internal order.
Maximum drift among shared selected scores is 0.00118597; related selected sets
match. This is existing service near-tie variability with identical scoring input,
not a retrieval change. No thresholds, parameters or prompts were adjusted.
For n=10 context reranks per side, live median latency is **45.688 → 49.842 ms**
(ranges 31.261–60.783 → 40.448–69.888). Generation n=3 per side:
2801.647/2526.883/2473.663 → 2865.153/2333.074/2511.529 ms. These small sequential
samples describe observed latency, not a capacity or performance improvement claim.

Newly composed synthetic content reaches actual BM25 in an offline integration
test and actual TEI stored-document embedding in a read-only service check:
two complete inputs, 1024 dimensions, 60.635 ms. Three rerank requests of 2 items
select both fact sources and preserve full context; latency 20.023/16.751/22.778 ms.
Three actual answers pass 9/9 checks, no forbidden claims; generation
2069.624/1763.212/2245.078 ms. Actual prompt token counts 1857/1851/1855 plus
500 reserved output tokens fit 8192. No source truncation, vector persistence or
chat endpoint was used. This is narrow synthetic-model evidence, not comprehensive
banking answer quality.

## Existing records and limitations

The read-only current signature matches the P3 PostgreSQL fingerprint
`948cae670aaec5faa350d977a0f381d6410a9b48d7853cdfd18bff7c76310750`:
**1526 chunks / 1526 Qdrant points, cross-store consistent**. SELECT-only taxonomy
inspection found 1526 recognized FAQs, zero missing parent categories, zero orphan
children, zero ambiguous footers, and one missing subcategory (chunk ID **225**).
Parent-only is valid, so that ID is a review candidate, not proven data loss.
Three available historical version rows all have both labels. No affected records
are proven from these observations; absence of a footer alone cannot establish
what it should have been. No repair or historical rewrite was performed.

If source evidence later identifies actual loss, propose an explicitly authorized
repair manifest mapping stable chunk ID + current hash to a trusted source/version
taxonomy, with per-record review and the normal coordinated write path. Do not
infer from a document title, guess missing paths, or bulk-fill from today's data.

Live transactional create/edit/revert and failure-injection checks remain blocked:
no isolated PostgreSQL/Qdrant fixtures with exclusive cleanup ownership are
established. Write consistency is covered by mocked repositories/vectors, actual
SQL construction, real HTTP middleware, and concurrency tests. Shared existing
KB records were untouched. Current-content/vector equality and tokenizer checks
do not prove distributed rollback correctness on the live stores.

Browser visual/accessibility verification, representative labeled answer quality,
real write-path latency, load/deadline and GPU-headroom checks remain release
limitations. Historical numbered-answer content is not automatically rewritten
by no-op or revert; the canonical outer answer format applies to new composition.
The production acceptance gate requires separate authorization and review.
