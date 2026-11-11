# 22. NegahBoom MODEL_CONTEXT_LIMIT repair (staging)

## Symptom

Every NegahBoom_FAQ question failed with `MODEL_CONTEXT_LIMIT` (HTTP 502). The
web UI showed "گفتگو برای پردازش طولانی است. پرسش کوتاه‌تری ارسال کنید.", which
blamed the user's question. It also failed on a new session with no history.

## Cause

vLLM ran with `--max-model-len 4000`. An answer request carries the system
prompt, ten reranked chunks (`RAG_CONTEXT_RERANK_TOP_K=10`), the question and the
reserved `RAG_MAX_NEW_TOKENS=500`. vLLM rejects the request with HTTP 400
(`param=input_tokens`) when prompt + `max_tokens` exceeds the limit.

Since `eee3e52` (2026-11-02) NegahBoom has had its own answer system prompt of
2208 tokens; the Hibank prompt is 1577. Counts below use the served tokenizer.

| Request | Prompt tokens | + 500 output | Fits 4000? |
|---|---:|---:|---|
| `چطوری وام بگیرم؟`, NegahBoom, before | 3569 | 4069 | no |
| NegahBoom, 10 largest chunks, before | 3911 | 4411 | no |
| `چطوری وام بگیرم؟`, NegahBoom, after | 2841 | 3341 | yes |
| NegahBoom, 10 largest chunks, after | about 3183 | about 3683 | yes |
| Hibank (General_FAQ), 10 largest chunks | 4892 | 5392 | no, needs more than 4000 |

Hibank normally fits only because its usual retrievals have small chunks.

## Changes

1. **NegahBoom answer prompt** (`NegahBoomPrompts.GENERAL_RAG_SYSTEM_PROMPT`):
   2208 → 1480 tokens. Same rules, written once: "service request" is defined
   once instead of repeating "digital-services or open-banking" about 40 times,
   and the duplicated identity and grounding text is merged. The introduction,
   company background, missing-information and out-of-scope sentences are taken
   from the module constants. The conflicting second introduction sentence in
   `<platform_identity>` was removed; rule 7 already required `INTRODUCTION`.
   The Hibank prompts are byte-identical.
2. **Regression test** `tests/test_prompt_token_budget.py`: with the served
   tokenizer, the NegahBoom answer prompt must stay no larger than Hibank's and at
   most 1700 tokens. It is skipped when the tokenizer file is absent
   (`PROMPT_BUDGET_TOKENIZER`).
3. **Web UI** (`static/js/api.js`): `MODEL_CONTEXT_LIMIT` no longer asks for a
   shorter question; `DEPENDENCY_INVALID_RESPONSE` and HTTP 502 now have Persian
   messages instead of the generic fallback.
4. **Staging vLLM** `--max-model-len` 4000 → **6144**. All other arguments and the
   image (`vllm/vllm-openai` v0.26.0, `sha256:ffb2d59b…`) are unchanged. 6144
   covers the Hibank worst case (5392) with room for longer questions.
   `RAG_CONTEXT_RERANK_TOP_K` stays 10. Production is not changed by this.

## Benchmark (vLLM only, one variable)

`benchmarks/vllm_context_length_benchmark.py`, same 66 saved payloads every run
(prompt 3366–3500 tokens, the pre-change NegahBoom prompt plus 10 chunks),
`max_tokens=500`, temperature 0, streamed. Each server was warmed first. The raw
JSON stays on the staging host in `benchmarks/results/vllm_max_model_len/`
(gitignored); the table below is the record.

Concurrency 50, 100 requests:

| `max_model_len` | Runs | Wall | p50 latency | p95 latency | p95 TTFT | Output tok/s |
|---|---:|---:|---:|---:|---:|---:|
| 4000 (original + fresh restart) | 3 | 11.7–12.2 s | 4.9–5.4 s | 9.0–9.4 s | 1.46–1.67 s | 403–419 |
| **6144** | 2 | 14.6–15.1 s | 6.3–7.0 s | 9.7–10.5 s | 1.88–1.92 s | 326–339 |
| 8192 | 2 | 21.2–22.3 s | 9.9–10.4 s | 16.5–17.1 s | 1.95–2.36 s | 221–232 |

At concurrency 1 and 16 all three settings are equal within run-to-run noise
(c=1 p50 1.69–1.73 s; c=16 p95 6.3–7.6 s). No request failed, vLLM logged no
preemption, and the scheduler config (`max_num_batched_tokens=2496`, CUDA graph
sizes) was identical. The c=50 decode slowdown therefore comes from
`max_model_len` itself. The fresh 4000 restart matched the original 4000
container, which rules out a restart effect. The 8192 setting was tested first
and rejected for this cost.

## Not yet done

- The retrieval and answer-quality evaluations
  (`docs/performance/RELEASE_EVALUATION_RUNBOOK.md`) need human labels and have
  not been run for the prompt change. A five-question smoke check returned
  grounded, prefixed answers and the exact fallback for an uncovered loan question.
- The full talk-endpoint load test was not run.
- Production: check its vLLM `--max-model-len` before releasing. The NegahBoom
  prompt fits 4000 in its worst case; Hibank's largest chunks need about 5400.

## Rollback

The original container is kept stopped as `gemma4-vllm-maxlen4000-backup`:

```bash
docker stop gemma4-vllm && docker rename gemma4-vllm gemma4-vllm-maxlen6144 \
  && docker rename gemma4-vllm-maxlen4000-backup gemma4-vllm && docker start gemma4-vllm
```
