# Persian Query Normalization Audit

## Outcome

The first meaningful divergence was the request-normalization output, before intent classification, TEI, or Qdrant.

- Query A remained `میشه اسم حساب هارو بگی`.
- Query B became `میشه اسم حساب‌ها رو بگی` in `PersianTextProcessor.normalize`.
- The semantic-search path then replaced B's ZWNJ with a space and sent `میشه اسم حساب ها رو بگی` to TEI, while A was sent unchanged.
- Their measured query-embedding cosine was `0.737751` in the initial exact-pair trace.
- Qdrant top-20 overlap was 13 IDs (Jaccard `0.4815`).
- Intended FAQ point `173` was semantic rank 20 / hybrid rank 6 for A, but outside B's semantic top 20 and hybrid top 10.

Both inputs classified as `general`. Qdrant returned results for both. The related-question reranker rejected every examined candidate at the unchanged `0.1` threshold, but that reranker controls only the related-question sidecar; it does not filter answer context. The defect was therefore a query-representation inconsistency that propagated into candidate selection, not a Qdrant outage, classifier route, or reranker-threshold failure.

## Audit protocol

| Item | Value |
|---|---|
| Repository revision | `1680198c46c1ba2f7fb65690634be7cc1b2b7697` plus pre-existing dirty-worktree changes |
| External deadline | 50 seconds |
| Staging hardware | One NVIDIA RTX 5880 Ada, 48 GB VRAM (repository fact; not independently probed) |
| Production hardware | Two NVIDIA L4, 24 GB each (not touched) |
| Embedding service | TEI 1.9.3, Jina v5 small retrieval, float16, last-token pooling, port 7997 |
| Reranking service | TEI 1.9.3, BGE reranker v2 m3, float16, port 7998 |
| Workload | Synthetic Persian FAQ queries, concurrency 1, fresh/empty history |
| Data access | PostgreSQL SELECTs, Qdrant queries, TEI inference, two sequential vLLM generations |
| Mutations | None to PostgreSQL, Qdrant, MinIO, `.env`, models, or running services |
| Trace IDs | `PQN-A-BASELINE`, `PQN-B-BASELINE`, `PQN-A-FINAL`, `PQN-B-FINAL` |

The user's reported B fallback was not reproduced deterministically on the first current-staging generation: that run answered from a different account-list chunk. The prompt uses `temperature=1`, so generation is not deterministic. The material retrieval/context divergence did reproduce. The reported fallback text exists only as an LLM prompt instruction; before this change there was no application reason code for it.

## End-to-end request map

| Order | Representation or operation | File / symbol | Finding |
|---:|---|---|---|
| 1 | Pydantic request | `main.QueryRequest`, `mobile_api.TalkRequest` | String validation only; mobile also checks truthiness. |
| 2 | Raw persistence | `main._query_documents`, `mobile_api._gateway_talk` | Raw/display query is persisted before answering. No canonical rewrite. |
| 3 | Trim and canonical query | `AnsweringService._answer` | Keeps `original_query`; creates `normalized_query`. This was the first A/B divergence before the fix. |
| 4 | Intent classification | `IntentClassifier.classify` | Uses the normalized query and a query-role TEI embedding. Both A/B route to `general`. |
| 5 | History rewrite | `HistoryRewritingService.rewrite_query` | Skipped for fresh history. Otherwise the normalized query is rewritten by vLLM; output is now normalized again. |
| 6 | Graph state | `AgentService`, `agent_graph.make_add_user_message` | Raw query remains in conversation messages; retrieval query is separate. |
| 7 | Rule expansion | `PersianHybridSearch._expand_query_intent` | Only three narrow terms: `انگشتم`, `رمزم`, `اس ام اس`. It did not affect A/B. |
| 8 | BM25 query | `PersianHybridSearch.process/search` | Parsivar normalization/tokenization, stopword removal, optional stemming. Stored FAQ corpus keeps its established path. |
| 9 | Embedding query | `_normalise_query`, `TeiEmbeddingClient.embed_query` | Canonical text, `prompt_name="query"`, `normalize=true`. |
| 10 | Qdrant | `_semantic_search` | Datasource filter, configured semantic limit 50, payload `chunk_id`. No vector threshold. |
| 11 | Hybrid fusion | `PersianHybridSearch.search` | Union of positive BM25 top 50 and semantic top 50; reciprocal-rank fusion with `k=60`; configured top 10. |
| 12 | Context formatting | `RAGSystem.generate_context` | All hybrid top-10 results become XML-like `<doc>/<question>/<answer>` context. No answer-context threshold. |
| 13 | Related reranking | `PersianHybridSearch.rerank` | Only the first five related-question records; threshold 0.1; output is UI sidecar only. |
| 14 | Prompt | `RAGSystem.answer` | FAQ prompt receives the retrieval query and all formatted top-10 context. |
| 15 | Generation/fallback | `RAGSystem.answer`, `agent_graph.make_handle_general` | vLLM decides whether to emit the prompt's exact fallback. New internal codes distinguish no retrieval from LLM context refusal. |
| 16 | Response/persistence | web/mobile route and `AgentService` | Raw query remains user-visible. Normalized text is not silently displayed in its place. |

## Exact pair: before

### Representations, classifier, and rewrite

| Field | Query A | Query B |
|---|---|---|
| Raw | `میشه اسم حساب هارو بگی` | `میشه اسم حساب ها رو بگی` |
| Parsivar normalized | `میشه اسم حساب هارو بگی` | `میشه اسم حساب‌ها رو بگی` |
| Rewrite | Not used (fresh history); same as normalized | Not used (fresh history); same as normalized |
| TEI retrieval input | `میشه اسم حساب هارو بگی` | `میشه اسم حساب ها رو بگی` |
| Intent | `general` | `general` |
| Actionable probability | `0.9994943` | `0.9999963` |
| Chitchat probability | `0.0005057` | `0.00000375` |
| Embedding norm | `1.00000003` | `1.00000004` |

Relevant code-point difference: A contains `هارو` as U+0647 U+0627 U+0631 U+0648 after a normal space. B's Parsivar form contains U+200C between `حساب` and `ها`; the old semantic path then changed U+200C to U+0020.

### Embedding similarity

| Comparison | Before | After |
|---|---:|---:|
| sim(A, B) | `0.737751` (repeat matrix `0.737812`) | `1.000000` |
| sim(A, matching FAQ question) | `0.391662` | `0.391596` |
| sim(B, matching FAQ question) | `0.522816` | `0.391596` |

The direct FAQ comparison embeds only the FAQ question with the query role. Qdrant point 173 stores an embedding of the full question-and-answer chunk with the document policy, so direct question similarity and Qdrant rank need not move together.

### Qdrant semantic top 20 before

| Rank | A ID / score | B ID / score |
|---:|---|---|
| 1 | 918 / 0.482872 | 918 / 0.616677 |
| 2 | 595 / 0.473054 | 595 / 0.613431 |
| 3 | 425 / 0.461942 | 1006 / 0.588003 |
| 4 | 1006 / 0.457108 | 816 / 0.575371 |
| 5 | 741 / 0.450853 | 425 / 0.568751 |
| 6 | 427 / 0.445644 | 1081 / 0.563290 |
| 7 | 816 / 0.432360 | 641 / 0.559050 |
| 8 | 426 / 0.430457 | 646 / 0.557730 |
| 9 | 1039 / 0.428424 | 704 / 0.551054 |
| 10 | 752 / 0.428035 | 427 / 0.550916 |
| 11 | 1081 / 0.427961 | 703 / 0.548955 |
| 12 | 742 / 0.427692 | 428 / 0.543824 |
| 13 | 428 / 0.425466 | 752 / 0.543675 |
| 14 | 646 / 0.425223 | 150 / 0.540708 |
| 15 | 152 / 0.423665 | 705 / 0.540586 |
| 16 | 955 / 0.423037 | 426 / 0.535206 |
| 17 | 1082 / 0.417712 | 424 / 0.531753 |
| 18 | 641 / 0.414906 | 748 / 0.530337 |
| 19 | 703 / 0.412876 | 149 / 0.530147 |
| 20 | **173 / 0.411496** | 97 / 0.528779 |

### Hybrid top 10 before

| Rank | A ID / hybrid / semantic / BM25 | B ID / hybrid / semantic / BM25 |
|---:|---|---|
| 1 | 703 / .028531 / .412876 / 1.506475 | 703 / .029469 / .548955 / 1.506475 |
| 2 | 918 / .026294 / .482872 / 1.403236 | 705 / .027032 / .540586 / 1.480540 |
| 3 | 68 / .025625 / .387130 / 1.501215 | 704 / .026838 / .551054 / 1.461335 |
| 4 | 97 / .025603 / .400128 / 1.478103 | 1078 / .026754 / .512242 / 1.490806 |
| 5 | 705 / .025196 / .395709 / 1.480540 | 150 / .026334 / .540708 / 1.473352 |
| 6 | **173 / .024846 / .411496 / 1.460426** | 918 / .026102 / .616677 / 1.403236 |
| 7 | 102 / .024658 / 0 / 1.522704 | 97 / .025833 / .528779 / 1.478103 |
| 8 | 595 / .024393 / .473054 / 0 | 81 / .025504 / .514954 / 1.475602 |
| 9 | 766 / .024393 / 0 / 1.520833 | 68 / .025356 / .496415 / 1.501215 |
| 10 | 425 / .024137 / .461942 / 0 | 149 / .025316 / .530147 / 1.467319 |

### Reranker before

Threshold remained `0.1`. A scores for IDs 703, 918, 68, 97, 705 were `0.0005093`, `0.0003830`, `0.0003102`, `0.0001881`, and `0.0001500`. B scores for IDs 704, 1078, 150, 703, 705 were `0.0822540`, `0.0035106`, `0.0008728`, `0.0002914`, and `0.0000969`. All were rejected as related suggestions. This did not remove any answer context.

### Context and fallback before

- A selected IDs: `703, 918, 68, 97, 705, 173, 102, 766, 595, 425`.
- B selected IDs: `703, 705, 704, 1078, 150, 918, 97, 81, 68, 149`.
- A context contained the intended two-account FAQ (point 173); B did not.
- Both had ten retrieval results, so `NO_RETRIEVAL_RESULTS` is false.
- The reported B fallback was the LLM's prompt-directed refusal because its selected context lacked the intended answer: new reason code `LLM_CONTEXT_REFUSAL`.
- On the initial current-staging replay, stochastic B generation instead answered from point 704. This does not alter the earlier retrieval divergence or the code-path diagnosis.

## Exact pair: after

Both normalize, classify, embed, retrieve, rerank, and format context from `میشه اسم حساب هارو بگی`.

- sim(A, B): `1.0`.
- Identical Qdrant top 20: yes.
- Identical hybrid/context IDs: yes.
- Intended point 173: hybrid rank 6 for both.
- Context SHA-256: `6e9ef5077108e9f0ad4569d0475b76dc22a4a0475b18adf3727efdd9bcc5c2ea` for both.
- Reranker scores and ordering: identical; no related suggestion passed 0.1.
- Final A and B answers both listed `حساب سپرده کوتاه مدت` and `حساب قرض الحسنه ویژه طرح آسمان بانک`.
- Final fallback: false for both.

## Every discovered text transformation

| Location | Scope | Transformation | Runtime relevance |
|---|---|---|---|
| `utils/persian_normalization.py` | Query/model boundary | NFKC, Arabic/Persian variants, Unicode spaces/invisibles, scoped Persian suffix and naming-question rules | New canonical source of truth |
| `AnsweringService._answer` | Online/web/mobile/batch query | Trim; Parsivar legacy normalization; canonical normalization; normalize rewrite again | Critical |
| `IntentClassifier.classify*` | Classifier input | Canonical normalization before TEI | Critical and defensive |
| `HistoryRewritingService.rewrite_query` | Rewrite input/output | Canonical input; canonical extracted output | Critical when history exists |
| `PersianTextProcessor.normalize` | BM25 corpus/query legacy layer | Parsivar; Arabic `ي/ى/ك`; Arabic digits to ASCII; whitespace collapse | Critical; corpus behavior intentionally preserved |
| `PersianHybridSearch._expand_query_intent` | Query | Narrow regex expansions for fingerprint/password/SMS colloquialisms | Did not affect reproduction |
| `PersianHybridSearch.process` | BM25 | Normalize, tokenize, stopword removal, optional stemming and suffix stripping | Critical hybrid branch |
| `PersianHybridSearch._normalise_query` | Semantic query | Canonical normalization | Critical semantic branch |
| `TeiEmbeddingClient.build_query_payload` | TEI query | Canonical input, query prompt name, unit-vector normalization | Critical defensive boundary |
| `PersianHybridSearch.rerank` | Reranker | Canonical query and candidate-question text | Related sidecar only |
| `RAGSystem.generate_context` | Retrieved chunks | Regex extraction and XML-like formatting; score sort | Critical prompt context |
| `RAGSystem.answer` | Prompt | Category-specific prompt; exact fallback instruction; answer cleanup | Critical generation |
| `utils.rag_utils.clean_llm_answer` | LLM output | Removes thought/think blocks and trims | Output only |
| `new_architecture/data_insertion_with_api.py`, `insert_data.py` | Index time | Parsivar-normalizes full chunk before document-role TEI embedding | Existing index policy, unchanged |
| `kb_manager.py` create/update/revert | Index time | Reconstructs raw QA; Parsivar-normalizes embedding input; stores raw text/payload | Existing live ingestion policy, unchanged |
| `hihelp_knowledge_changer.py`, `hihelp_chunker.py` | Source/chunk generation | Replace ZWNJ with spaces; strip cells; write raw chunks | Offline/source preparation |
| `creating_chunking_ready_file_from_general_questions_file.py` | Legacy source conversion | Replace ZWNJ with spaces | Legacy/offline |
| `new_architecture/app/services/chunking/chunker.py`, `utils/extract_text_chunks.py` | Document extraction | Strip and replace ZWNJ with spaces in extracted sections | Non-FAQ ingestion |
| `training/intent_classifier/common.py` | Training comparisons | NFKC, Arabic variants, removes ZWNJ/bidi/BOM, optional punctuation removal, whitespace/casefold | Training only; not live representation |
| `training/intent_classifier/build_training_dataset.py` | Training augmentation | Whitespace, punctuation, ZWNJ and first `می ` variations | Training only |
| `mass_answer_files.normalize_column_name` | Uploaded column names | NFKC, Arabic variants, whitespace, casefold | Header matching only, not user query |

## Index-time versus query-time

| Stage | Index-time representation | Query-time representation | Consistent? |
|---|---|---|---|
| Stored chunk/payload | Raw reconstructed/source text | Raw user text preserved separately | Intentionally different roles |
| BM25 | Legacy Parsivar processing for every chunk | Canonical query followed by the same legacy tokenizer/stemmer | Tokenizer symmetric; query has an added orthographic canonical layer |
| TEI embedding | Parsivar-normalized full chunk, document policy, no prompt name | Canonical query, query policy, `prompt_name=query` | Intentionally role-asymmetric; prompt policy was previously benchmarked |
| Reranker | Live candidate question normalized canonically | Live query normalized canonically | Yes after fix |
| Classifier | No index-time equivalent | Canonical query | Not applicable |
| Rewrite | No index-time equivalent | Canonical before and after | Not applicable |

Query-side normalization is sufficient for this defect; no reindex is required. The chosen canonical form maps variants onto the representation already proven to retrieve the existing point 173. Existing document vectors and their established document-role policy are unchanged.

## `.gitkeep` and filesystem findings

The `General_FAQ/.gitkeep` deletion and generated chunk files were present before this work. `.gitkeep` is hidden/empty, is ignored by the knowledge-source discovery and intent-training readers, is never embedded, and cannot affect Qdrant candidates. The matching FAQ file and PostgreSQL/Qdrant point were present and readable. `.gitkeep`, chunk discovery, and file ingestion are ruled out as causes.

## Fallback reason codes and observability

The graph now records:

- `NO_RETRIEVAL_RESULTS` when the hybrid result list is empty.
- `LLM_CONTEXT_REFUSAL` when the configured FAQ fallback phrase is generated despite non-empty retrieval.

Existing service exceptions already distinguish timeout/unavailable/invalid-request paths. Request traces now carry only content-free diagnostics: raw/normalized/rewritten query fingerprints, rewrite-used flag, top retrieval IDs/scores, selected context IDs, rerank IDs/scores/acceptance, threshold, and fallback reason. Full query or prompt text is not added to INFO logs.

## Safety decisions

No retrieval thresholds, top-k limits, semantic candidate limits, model architecture, model weights, prompts, `.env`, or Qdrant data were changed. No global `رو → را` rule was added. No stemming, broad typo correction, punctuation deletion, number conversion, or URL manipulation was added.

