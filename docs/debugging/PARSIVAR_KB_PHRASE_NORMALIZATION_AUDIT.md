# Parsivar and KB Phrase Normalization Audit

## Outcome

Parsivar is installed (`0.2.3.1`) and is active on every online web, mobile,
and mass-answer request through `AnsweringService`. It remains the first query
preprocessing layer. It handles some suffix spacing but does not restore
accidentally concatenated domain phrases. A generated, answer-free,
high-confidence KB phrase layer now runs after existing general/Parsivar
processing.

## Every Parsivar code location

| Location | Import/instance | Calls | Runtime role |
|---|---|---|---|
| `utils/persian_hybrid_search.py` | Imports `Normalizer`, `Tokenizer`, `FindStems`; each `PersianTextProcessor` constructs them | Normalization, tokenization, optional stemming | Active online. One processor is the `AnsweringService` preprocessor and another belongs to hybrid search. |
| `new_architecture/data_insertion_with_api.py` | Local Parsivar import and `Normalizer()` | Normalizes each complete chunk before document embedding | Active when this insertion script runs. |
| `new_architecture/insert_data.py` | Local Parsivar import and `Normalizer()` | Normalizes each complete chunk before document embedding | Active when this insertion script runs. |
| `kb_manager.py` | Module-level `Normalizer()` | Create, update, and revert normalize reconstructed content before embedding | Active KB-management path. Raw content remains stored. |
| `benchmarks/embedding/tei_query_task_equivalence.py` | Optional benchmark-local `Normalizer()` | Normalizes benchmark documents | Diagnostic only. |

README, requirements, tests, historical proposals, and documentation mention
Parsivar but do not introduce another application call path.

## Exact online boundary map

| Requested stage | Parsivar applied? | Exact behavior |
|---|---|---|
| User query before intent classification | Yes | `AnsweringService._answer` calls `PersianTextProcessor.normalize`, then the Unicode/suffix/KB layer, then the classifier. Direct standalone classifier calls do not instantiate Parsivar. |
| User query before query rewriting | Yes | The same canonical result becomes `current_query`. |
| Rewritten query | Not directly | LLM rewrite output passes through the deterministic Unicode/suffix/KB layer. Retrieval subsequently applies its own Parsivar processor. |
| Embedding input | Yes on the online path | Hybrid search applies `processor.normalize` again, then canonical normalization; the TEI payload builder defensively canonicalizes once more. |
| Qdrant search input | Indirectly | Qdrant receives only the TEI vector, not query text. The vector comes from the Parsivar-plus-canonical embedding string. |
| Reranker query input | Yes upstream, not inside `rerank` | The online query is already Parsivar-normalized; `rerank` defensively canonicalizes it and sends that string to TEI. |
| FAQ ingestion/embedding | Yes | Both insertion scripts and KB create/update/revert use Parsivar on the full question/answer chunk before document embedding. They do not use query-only colloquial rules. |

## Supplied representations

`\u200c` denotes ZWNJ. Classifier, embedding, and reranker values are the actual
post-fix online representations.

| Raw | Parsivar output | Classifier input | Embedding input | Reranker query |
|---|---|---|---|---|
| `میشه اسم حساب هارو بگی` | same | `میشه اسم حساب هارو بگی` | same | same |
| `میشه اسم حساب ها رو بگی` | `میشه اسم حساب\u200cها رو بگی` | `میشه اسم حساب هارو بگی` | same | same |
| `میشه اسم حساب‌ها رو بگی` | same, with ZWNJ | `میشه اسم حساب هارو بگی` | same | same |
| `میشه اسم حسابها رو بگی` | same | `میشه اسم حساب هارو بگی` | same | same |
| `سفر فصلی چیه` | same | `سفر فصلی چیه` | same | same |
| `سفرفصلی چیه` | same | `سفر فصلی چیه` | same | same |

Live staging classifier results with the current checkpoint:

- All four account forms: `general`, confidence `0.9994943142`.
- Both travel forms: `general`, confidence `0.9990590215`.

Parsivar alone makes neither family fully equivalent. It inserts the expected
half-space for separated `حساب ها`, but leaves attached `حسابها`, attached
`هارو`, and `سفرفصلی` different.

## KB phrase derivation

The deterministic builder parsed all 1,426 valid FAQ chunks. It ignores hidden,
empty, temporary, and non-text files by policy; none were present in this
snapshot. Answers are not used for discovery and are absent from the artifact.

| Gate | Count |
|---|---:|
| Valid FAQ files | 1,426 |
| Discovered metadata/repeated-question candidates | 2,610 |
| Accepted high-confidence phrases | 100 |
| Rejected as insufficiently supported or ambiguous | 2,510 |

Acceptance requires a safe two-to-four-word Persian shape plus one of:

- category occurrence in at least two chunks;
- exact subcategory occurrence in at least three chunks; or
- an explicitly reviewed banking term observed in current FAQ questions.

| Variant | Canonical | Evidence |
|---|---|---|
| `احرازهویت`, `احراز‌هویت` | `احراز هویت` | category, subcategory, question; frequency 92 |
| `افتتاححساب`, `افتتاح‌حساب` | `افتتاح حساب` | category, subcategory, question; frequency 98 |
| `شمارهحساب`, `شماره‌حساب` | `شماره حساب` | question; frequency 7 |
| `قرضالحسنه`, `قرض‌الحسنه` | `قرض الحسنه` | question; frequency 16 |
| `سفرفصلی`, `سفر‌فصلی` | `سفر فصلی` | question; frequency 22 |

`سفر فصلی من` is a current KB category with 22 chunks. Thus the travel example
is not out-of-domain in this snapshot; boundary restoration is KB-backed rather
than generic dictionary segmentation. Unknown compounds such as
`کتابخانهکودک` remain unchanged.

## Caching and complexity

The artifact is loaded and its regex compiled once at module import. FAQ files
are never scanned per request. Seven 10,000-iteration measurements produced a
median `33.760 µs/query` and maximum `36.892 µs/query`, versus approximately
`22.057 µs/query` before the lexicon. The roughly `11.7 µs` incremental cost is
negligible relative to network inference and retrieval.

## Ingestion and reindex decision

Existing vectors use Parsivar-normalized complete documents, while query
vectors use query-role TEI policy and conservative query canonicalization. This
role asymmetry is intentional. The lexicon maps malformed user input to normal
phrases already present throughout source questions; it does not change stored
text or vector semantics. Live account retrieval remains identical.

Decision: query-side normalization is sufficient and Qdrant reindexing is not
required. Ingestion was audited but not changed. No Qdrant mutation occurred.

## Intent training augmentation

The deterministic dataset builder now emits concatenated, ZWNJ, and extra-space
variants for approved banking phrases and for multi-word non-banking entities.
These are training-data changes only. The checkpoint was not retrained or
overwritten. Generic runtime word segmentation was deliberately not added.
