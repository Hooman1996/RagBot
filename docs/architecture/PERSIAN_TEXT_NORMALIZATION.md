# Persian Text Normalization Architecture

## Representations

The application maintains separate representations:

| Name | Purpose |
|---|---|
| `original_query` / raw query | Persistence, conversation history, response echo, and user-visible style |
| `normalized_query` | Intent classification and rewrite input |
| `rewritten_query` | Context-resolved query; normalized again before retrieval |
| semantic query | Canonical query sent to query-role TEI and Qdrant |
| BM25 query | Canonical query tokenized by the established Parsivar/BM25 pipeline |

Raw text must not be overwritten globally. Canonical text is for model and retrieval boundaries.

## Canonical normalizer

`utils.persian_normalization.normalize_persian_text` is deterministic, stateless, thread-safe, dependency-light, and close to O(n) for normal inputs. It uses precompiled regular expressions and Python's `unicodedata`; it performs no network or model call.

Its final stage delegates to an immutable KB phrase normalizer. The generated
artifact is loaded and compiled once at import; it never scans FAQ files during
a request. The artifact derives only from current FAQ questions, categories,
and subcategories, never answers.

Rules:

1. Apply Unicode NFKC.
2. Map Arabic `ي/ى/ك` to Persian `ی/ی/ک`.
3. Convert Unicode separator characters and whitespace (including NBSP) to normal spaces; collapse repeats and trim.
4. Treat accidental ZWJ as ZWNJ; remove bidi-formatting marks, word joiner, and BOM.
5. Canonicalize plural `ها` and `های` spacing to ZWNJ when no object marker follows.
6. Canonicalize plural-object variants (`ها رو`, `ها‌رو`, `هارو`, `ها را`) to the measured retrieval form with an attached colloquial object marker, such as `حساب هارو`.
7. Canonicalize `می شه`, `می‌شه`, `میشه`, `می شود`, and `می‌شود` to `میشه`.
8. Canonicalize the narrow grammatical form `اسم <plural> چیست/چیه؟` to an equivalent naming-request form while preserving the entity.
9. Restore only lexicon-approved multi-word concepts when a boundary is a
   space, ZWNJ, repeated space, or accidentally absent.

The `رو/را` rule is scoped to an explicit plural-object construction. Standalone `رو` is unchanged. A lexical guard prevents `تنها رو` from being misparsed as a plural.

## Deliberately omitted rules

- No global `رو → را` replacement.
- No global punctuation deletion or ASCII/Persian punctuation conversion; this protects URLs, query strings, decimal/group separators, and identifiers.
- No stemming or lemmatization in the canonical utility.
- No general spelling correction, typo model, keyboard-layout conversion, or edit-distance rewrite.
- No banking synonym expansion or hard-coded FAQ phrase.
- No number-script conversion in the canonical utility. Raw structured values remain intact; the older Parsivar layer may retain its established query behavior.
- No generic Persian word segmentation. Unknown concatenated tokens remain
  unchanged even when a possible dictionary split exists.
- No change to retrieval thresholds, top-k, candidate limits, embedding/reranking models, prompts, or weights.

## Boundary policy

```text
raw query
  -> legacy Parsivar normalization
  -> canonical Persian normalization
  -> intent classifier
  -> optional history rewrite
  -> canonical Persian normalization
  -> BM25 + query-role TEI/Qdrant
  -> canonical query/candidate questions for related reranker
  -> answer context and prompt
```

The TEI query-payload builder also canonicalizes defensively so direct classifier or retrieval callers cannot bypass the policy. Stored-document embedding payloads remain unchanged to preserve compatibility with the existing collection.

## Index compatibility and reindex decision

Decision: **A — query-side normalization is sufficient; no reindex required.**

Existing vectors were generated from Parsivar-normalized full chunks using the document embedding policy. The fixed queries are mapped to the already-working A representation; point 173 remains in the existing hybrid top 10. Neither stored chunks nor vectors changed.

Future ingestion continues using the existing Parsivar/document-role policy. This is intentionally not byte-identical to query representation because query and document roles already use different, measured TEI policies. The symmetry required for this issue is that all equivalent user-query forms share one query representation and that the reranker sees the same canonical query/candidate form.

## Fallback reasons

Internal graph state now records:

| Code | Condition |
|---|---|
| `NO_RETRIEVAL_RESULTS` | Hybrid retrieval returned no chunks |
| `LLM_CONTEXT_REFUSAL` | Non-empty retrieval reached vLLM, which emitted the configured FAQ refusal phrase |

These codes are included in sanitized operator traces and are not exposed in the end-user API.

## Observability and privacy

The request trace records:

- raw, normalized, and rewritten query SHA-256 prefixes;
- whether rewrite changed the query;
- retrieval point IDs and BM25/semantic/hybrid scores;
- selected context IDs;
- related-reranker IDs, scores, threshold decisions;
- fallback reason.

It does not add full query, context, prompt, customer data, authentication values, or banking data to INFO logs.

## Performance

On this host, seven 10,000-call mixed-query runs measured a median `33.760 µs`
per normalization and a worst run of `36.892 µs`. The cached KB phrase layer
adds about `11.7 µs` over the earlier Unicode/suffix-only measurement. This is
negligible relative to TEI, Qdrant, reranking, and vLLM latency.

## Deployment

1. Run the targeted unit/contract tests.
2. Run the read-only staging equivalence diagnostic.
3. Deploy the Python changes to staging.
4. Restart the FastAPI application so imported code is refreshed.
5. Smoke-test the exact A/B pair with fresh sessions and the same `General_FAQ` datasource.
6. Confirm identical normalized fingerprints, context IDs, and point 173 presence in request traces.
7. Monitor `LLM_CONTEXT_REFUSAL`, `NO_RETRIEVAL_RESULTS`, and retrieval IDs before production promotion.

No Qdrant deletion/reindex, `.env` edit, model restart, model-weight change, or production infrastructure action is part of this deployment.
