# TEI query-task equivalence audit

Date: 2026-07-29  
Repository revision: `f3f810eafb7254cdf691a680e01d702ebe87900f`  
Workload: 10 synthetic Persian banking FAQ queries  
Environment: staging host `silicon1`; no production service was contacted or changed  
External application timeout: 50 seconds (not exercised by this embedding-only audit)

## Executive conclusion

The previous local call and the current raw TEI call are semantically
equivalent for the exact installed model, within the expected numerical
difference between local CPU inference and TEI float16 inference.

The reason is model-specific: the installed SentenceTransformers graph has no
`Router` module. SentenceTransformers 5.2.0 permits a `task` keyword even when
no module consumes it, so `task="retrieval.query"` and
`task="retrieval.passage"` do not select a prompt or adapter for this model.
They encode raw text. In contrast, `prompt_name="query"` prepends the model's
declared `Query: ` prompt, and `prompt_name="document"` prepends `Document: `.

Measured evidence:

- Local `task="retrieval.query"` versus local raw input: cosine
  `1.000000` for all 10 queries.
- Local method A versus raw TEI method B: mean cosine `0.999646`, range
  `0.998570–0.999948`, and mean overlap@10 `0.99`.
- A and B produced identical retrieval metrics.
- `prompt_name="query"` and a manual `Query: ` prefix were mutually
  equivalent: cosine `0.9999987–0.9999993`.
- The query prompt improved the manually reviewed 10-query retrieval set:
  top-1 accuracy `0.50 → 0.80`, top-3 accuracy `0.90 → 1.00`,
  Recall@3 `0.65 → 0.80`, Recall@10 `0.85 → 0.95`, and
  MRR@10 `0.6833 → 0.8833`.
- Ten sampled stored Qdrant vectors matched normalized raw document text at
  mean cosine `0.999949`. Local `task="retrieval.passage"` was exactly the
  same as local raw text, while explicit `prompt_name="document"` matched the
  stored vectors less closely (mean cosine `0.987084`).

No production code was changed.

## Exact runtime and model

### TEI service

| Item | Observed value | Evidence status |
|---|---|---|
| Container | `tei-embedding` | observed |
| Image tag | `ghcr.io/huggingface/text-embeddings-inference:cuda-1.9` | observed |
| Image digest | `sha256:249a0bc87522bfe2f1012b4d194f0225878f47079115ada3aeb0b1ef257b402a` | observed |
| TEI version | `1.9.3` | observed from installed binary and `/info` |
| TEI revision | `06670157fb6c1523482219bdb2d1660277d38088` | observed from image label and `/info` |
| Model path | `/app/models/models--jinaai--jina-embeddings-v5-text-small-retrieval` | observed |
| Model revision/SHA | unavailable (`model_sha: null`) | unknown |
| Serving dtype | `float16` | observed from `/info` |
| Pooling | `last_token` | observed from `/info` |
| Maximum input length | 16,384 tokens | observed from `/info` |
| Maximum batch tokens | 16,384 | observed from `/info` |
| Max client batch size | 50 | observed |
| Max concurrent requests | 100 | observed |
| Auto-truncate | enabled | observed |

The exact startup command is:

```text
./entrypoint.sh \
  --model-id /app/models/models--jinaai--jina-embeddings-v5-text-small-retrieval \
  --max-client-batch-size 50 \
  --max-concurrent-requests 100
```

No `--pooling`, `--default-prompt`, or `--default-prompt-name` override is
present. The installed TEI help states that, without `--pooling`, TEI reads
`1_Pooling/config.json`; the live `/info` response confirms `last_token`.
Without a default prompt flag, raw requests receive no prompt.

At measurement time the staging GPU was an NVIDIA RTX 5880 Ada Generation,
compute capability 8.9, driver 595.58.03, with 49,140 MiB total,
1,548 MiB used, 46,964 MiB free, and 0% utilization. This is staging-specific
runtime evidence and is not transferable as a serving configuration to the
two separate 24 GB L4 production GPUs.

### Local model files

Model directory:
`/root/models/models--jinaai--jina-embeddings-v5-text-small-retrieval`

| File | Relevant contents | SHA-256 |
|---|---|---|
| `config.json` | `Qwen3Model`, hidden size 1024, BF16 metadata, model max position 32,768, task name `retrieval` | `f59f2ca97a4c6bdaa97722d1f8a93ff8823612a4ccba94e0af1f338d226aec56` |
| `tokenizer_config.json` | `Qwen2Tokenizer`, pad token `<\|endoftext\|>`, EOS `<\|im_end\|>`, tokenizer max 131,072 | `1cc816812993bff176eb4f7495433b736f06fba9b6e7b05cac7b4a1780650c95` |
| `config_sentence_transformers.json` | prompts `query: "Query: "`, `document: "Document: "`; no default prompt; cosine similarity | `916dede36f621cdfecd30fde3d66923dc45336fe75e051b8839374800148b560` |
| `modules.json` | Transformer → Pooling → Normalize; no Router | `84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf` |
| `1_Pooling/config.json` | 1024 dimensions; only last-token pooling enabled; prompt included | `37bf193fa101f19101bfad9c31d3eb0f786e247b7b1e5cb7f007d730eed1ddbd` |
| `model.safetensors` | 1,192,133,232 bytes | `0362107c2b13e18284c5152c4d4f667a4dec4665abdfe4f5e43a9bb799ba2276` |

The local benchmark runtime was Python 3.12.12, PyTorch 2.9.1+cu130,
Transformers 5.10.1, and SentenceTransformers 5.2.0. The model's saved
SentenceTransformers metadata records 5.1.2, but the actual invoked local
runtime was 5.2.0.

The model README included in the installed directory uses
`prompt_name="query"` for queries and `prompt_name="document"` for documents.
It does not define a prompt named `passage`.

## Answers to the verification questions

1. **Does TEI support `prompt_name` for this model?** Yes. TEI 1.9.3 accepts
   `prompt_name="query"` and applies the configured prompt. The exact installed
   model README also documents this TEI request. The live request succeeded.

2. **Exact query prompt name:** `query`, whose text is exactly `Query: `
   (capital Q, colon, trailing ASCII space).

3. **Exact document/passage prompt name:** `document`, whose text is exactly
   `Document: `. There is no `passage` prompt key.

4. **Is `prompt_name="query"` equivalent to
   `task="retrieval.query"`?** No. For this module graph,
   `task="retrieval.query"` is unused and is equivalent to raw input.
   `prompt_name="query"` changes the input tokens. The measured mean
   cosine between the two was `0.784006`, with a wide
   `0.071633–0.986024` range.

5. **Does TEI automatically normalize?** Yes. With the request property
   omitted, the measured vector norm was `1.000000004`, identical to the
   `normalize: true` probe. This agrees with the model's Normalize module and
   TEI's default behavior for `/embed`.

6. **Is the `normalize` property supported by installed TEI?** Yes,
   empirically. `normalize: false` was accepted and produced norm
   `48.866655`; `normalize: true` produced norm `1.000000004`. The TEI server
   exposes no OpenAPI document at `/openapi.json` (404), so the live
   request/response test is the version-specific evidence.

7. **Is last-token pooling correct?** Yes. The local pooling file enables
   only `pooling_mode_lasttoken`; TEI was started without an override; installed
   help says this file is used by default; live `/info` reports
   `pooling: last_token`.

8. **Do TEI and the previous implementation use the same dimension?** Yes.
   Every A/B/C/D vector was 1024-dimensional. The model hidden/pooling
   dimension is 1024, the application validates 1024, and Qdrant is 1024.

9. **How were existing Qdrant vectors generated?** Their effective semantics
   are normalized raw document text. The offline ingestion source invokes
   `task="retrieval.passage"`, but that argument is unused for this model and
   produces a vector identical to raw text. Ten stored-vector samples matched
   local normalized raw documents at mean cosine `0.999949` (minimum
   `0.999937`). The same samples matched explicit `document` prompting at mean
   cosine `0.987084`. The payload/ID layout and count (960 points, matching 960
   FAQ chunks) agree with the ingestion script. Runtime provenance proving
   which historical process invocation created every live point is not stored,
   so the invocation label is inferred; effective raw semantics are measured.

10. **Are current query and document prompts compatible?** Current query
    embedding is raw TEI input. Existing documents are effectively raw, and
    knowledge-base create/update/revert also call the raw TEI encoder.
    Therefore the current raw/raw setup is internally consistent and matches
    the old effective behavior. It does not use the model author's intended
    query/document prompt pair. In this collection, using the query prompt
    against existing raw document vectors nevertheless improved all measured
    retrieval metrics.

11. **Does this migration require rebuilding Qdrant?** No. The migration from
    local `task="retrieval.query"` to raw TEI preserved effective query
    semantics and dimensions. The stored vectors also match raw document
    semantics. The measured query-prompt improvement works against the existing
    collection without rebuilding it.

## Application-path inspection

- Current async query embedding:
  `utils/persian_hybrid_search.py:292-312` posts
  `{"inputs": query, "normalize": true}` with no prompt.
- Previous local query code remains visible at
  `utils/persian_hybrid_search.py:403-410`.
- Dense search sends that vector to Qdrant at
  `utils/persian_hybrid_search.py:447-465`.
- Offline ingestion normalizes document text and calls
  `task="retrieval.passage"` at
  `new_architecture/insert_data.py:1142-1156`; the parallel
  `data_insertion_with_api.py` path does the same.
- Knowledge-base create, update, and revert use the query encoder for document
  content at `kb_manager.py:187`, `kb_manager.py:270`, and
  `kb_manager.py:425`, so they currently generate raw normalized document
  vectors.

This produces one latent maintenance hazard: if query embedding is changed to
use the query prompt later, the knowledge-base mutation path must not inherit
that behavior for documents. It needs an explicit document-embedding contract.
That production change is intentionally outside this audit.

## Qdrant inspection

The live `hihelp_embeddings` collection was green and contained 960 points in
8 segments. It uses:

```json
{
  "size": 1024,
  "distance": "Cosine"
}
```

No quantization is configured. Because there are fewer than the 10,000-point
full-scan threshold, Qdrant reported zero indexed vectors; this does not affect
the semantic-equivalence conclusion.

## Comparison protocol

The representative query fixture is
[`benchmarks/embedding/fixtures/persian_faq_retrieval_eval.json`](../../benchmarks/embedding/fixtures/persian_faq_retrieval_eval.json).
It derives 10 non-customer Persian queries from the existing mobile-talk
benchmark fixture and adds manually reviewed relevant Qdrant point IDs.

Methods:

- A: local SentenceTransformer on CPU,
  `task="retrieval.query"`, normalized.
- B: TEI raw inputs, no `prompt_name`, `normalize: true`.
- C: TEI raw query plus `prompt_name="query"`, `normalize: true`.
- D: TEI input manually prefixed with `Query: `, no `prompt_name`,
  `normalize: true`.

The local stage additionally encoded raw and `prompt_name="query"` controls to
prove the local task behavior. Ten normalized FAQ documents were encoded as
raw text, `task="retrieval.passage"`, and `prompt_name="document"` and compared
with their stored Qdrant vectors.

The comparison script is
[`benchmarks/embedding/tei_query_task_equivalence.py`](../../benchmarks/embedding/tei_query_task_equivalence.py).
It records monotonic elapsed time, validates vector shapes and finite values,
performs top-10 Qdrant searches, and calculates rank/score changes and quality
metrics.

## Per-query measured results

All A vectors had dimension 1024 and norms in `0.998066–1.003548`; all TEI
vectors had dimension 1024 and norm 1.000000 to displayed precision.

| Query | cos A/B | cos A/C | cos A/D | overlap@10 A/B | overlap@10 A/C | overlap@10 A/D |
|---|---:|---:|---:|---:|---:|---:|
| balance | 0.999936 | 0.968643 | 0.968653 | 1.00 | 1.00 | 1.00 |
| card-replacement | 0.999903 | 0.885492 | 0.885496 | 1.00 | 0.90 | 0.90 |
| transfer-limit | 0.998570 | 0.321472 | 0.321526 | 1.00 | 0.90 | 0.90 |
| joint-account | 0.999941 | 0.986024 | 0.986021 | 1.00 | 1.00 | 1.00 |
| password-reset | 0.999820 | 0.950918 | 0.950922 | 1.00 | 1.00 | 1.00 |
| cheque-status | 0.999941 | 0.974067 | 0.974069 | 1.00 | 1.00 | 1.00 |
| mobile-banking | 0.999900 | 0.929703 | 0.929711 | 1.00 | 0.70 | 0.70 |
| deposit-profit | 0.998677 | 0.071633 | 0.071637 | 0.90 | 0.00 | 0.00 |
| iban | 0.999820 | 0.770992 | 0.770996 | 1.00 | 0.90 | 0.90 |
| transaction-history | 0.999948 | 0.981114 | 0.981122 | 1.00 | 1.00 | 0.90 |

The complete per-query report contains:

- all A/B/C/D `ID@score` top-10 lists;
- moved, entered, and exited result counts;
- mean and maximum absolute Qdrant score changes for B/C/D relative to A.

It is saved as
[`measured-results.md`](../../benchmarks/results/inference/embedding-task-equivalence/20260729T063500Z/measured-results.md).
The machine-readable
[`analysis.json`](../../benchmarks/results/inference/embedding-task-equivalence/20260729T063500Z/analysis.json)
contains every per-ID old/new rank, rank delta, old/new score, and score delta.
Raw vectors are intentionally kept out of this narrative but are preserved in
the run directory.

The strongest rank change was `deposit-profit`: A/B failed to retrieve the
manually relevant point 74 in the top 10, while C/D ranked point 74 first.
For `transfer-limit`, C/D moved the relevant point 203 from rank 2 to rank 1.
A and B differed only by float-backend noise: nine queries had identical
top-10 membership, and the tenth had one entry/exit.

## Retrieval evaluation

Metrics use multiple relevant IDs where the FAQ corpus contains valid
alternative answers. Recall is the mean per-query fraction of relevant IDs
retrieved. MRR is capped at rank 10.

| Method | Top-1 accuracy | Top-3 accuracy | Recall@3 | Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|
| A — local `task="retrieval.query"` | 0.50 | 0.90 | 0.65 | 0.85 | 0.6833 |
| B — raw TEI | 0.50 | 0.90 | 0.65 | 0.85 | 0.6833 |
| C — TEI `prompt_name="query"` | 0.80 | 1.00 | 0.80 | 0.95 | 0.8833 |
| D — manual `Query: ` | 0.80 | 1.00 | 0.80 | 0.95 | 0.8833 |

This is a small, manually labeled retrieval set. It is suitable for the
migration decision because A/B equivalence and the C/D improvement are large
and internally controlled, but it is not a replacement for a broader
domain-quality suite. No repository-defined answer-quality test command exists,
so answer quality remains unknown. Production-code adoption remains gated on
that missing answer-quality test.

## Safe staged execution

The measured run used CPU for A, so no GPU service had to be stopped:

```bash
RUN_DIR=benchmarks/results/inference/embedding-task-equivalence/<UTC-timestamp>
mkdir -p "$RUN_DIR"

/root/miniconda3/envs/faq/bin/python \
  benchmarks/embedding/tei_query_task_equivalence.py local \
  --fixture benchmarks/embedding/fixtures/persian_faq_retrieval_eval.json \
  --model /root/models/models--jinaai--jina-embeddings-v5-text-small-retrieval \
  --output "$RUN_DIR/local.json" \
  --device cpu

# Run only after the local process has exited.
/root/miniconda3/envs/faq/bin/python \
  benchmarks/embedding/tei_query_task_equivalence.py tei \
  --fixture benchmarks/embedding/fixtures/persian_faq_retrieval_eval.json \
  --tei-url http://127.0.0.1:7997 \
  --output "$RUN_DIR/tei.json"

/root/miniconda3/envs/faq/bin/python \
  benchmarks/embedding/tei_query_task_equivalence.py analyze \
  --fixture benchmarks/embedding/fixtures/persian_faq_retrieval_eval.json \
  --local-results "$RUN_DIR/local.json" \
  --tei-results "$RUN_DIR/tei.json" \
  --qdrant-url http://127.0.0.1:6333 \
  --collection hihelp_embeddings \
  --output "$RUN_DIR/analysis.json" \
  --markdown-output "$RUN_DIR/measured-results.md"
```

The script refuses `--device cuda...` unless
`--tei-confirmed-stopped` is supplied. If a future operator requires local GPU
inference, they must first capture current container/GPU state and exact
restart commands, prove the targets are staging, obtain review, stop all
GPU-resident TEI/vLLM services, verify free VRAM, run only the local stage,
release the model process, restore the original services, verify health, and
then run the TEI stage. This audit did not stop or reconfigure any service.

## Validation and limitations

- The comparison script compiled successfully with the project environment.
- Unit tests were added at
  [`tests/benchmarks/test_tei_query_task_equivalence.py`](../../tests/benchmarks/test_tei_query_task_equivalence.py)
  for cosine validation, overlap@10, rank/score deltas, multi-relevance
  retrieval metrics, and vector-shape validation.
- Neither available Python environment has pytest installed, so the pytest
  command could not be run. Direct function-level assertions were used
  separately; pytest status is not claimed.
- TEI exposes no OpenAPI JSON at `/openapi.json`; installed binary help,
  live `/info`, exact local model files, and controlled API probes provide the
  version-specific evidence instead.
- No answer-quality suite or command exists in the repository. This blocks a
  model-behavior production change, but not the audit conclusion.

## Recommendation

**use `prompt_name="query"`**

It is natively supported by installed TEI 1.9.3, is equivalent to the model's
documented `Query: ` formatting, avoids manual prompt duplication, requires no
Qdrant rebuild for the measured collection, and improved every reported
retrieval metric over both the previous local behavior and current raw TEI
behavior.
