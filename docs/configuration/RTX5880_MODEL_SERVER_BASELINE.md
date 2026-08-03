# RTX 5880 model-server baseline

This file documents externally managed vLLM and TEI settings. None of these
flags is controlled by `.env`; placing them there would have no effect.
Observed settings are facts. Proposed ranges are experiments, not final values.

> **Measured update:** vLLM was subsequently started and inspected. The running
> vLLM 0.26.0 command uses tensor parallelism 1, model length 4000,
> `max_num_seqs=100`, GPU-memory utilization 0.75, FP8 KV cache, and prefix
> caching. The unchanged model-server configuration passed the strict
> five-wave application target when FastAPI used request limit 50 and HTTP
> pools 64. See `RTX5880_FINAL_RECOMMENDATIONS.md`. Later “vLLM not running”
> statements below describe the earlier audit capture only.

## Runtime capture

### GPU sharing

At the 2026-07-29 idle capture:

- GPU: NVIDIA RTX 5880 Ada Generation, 49,140 MiB reported.
- TEI embedding: 1,538 MiB.
- TEI reranker: 1,506 MiB.
- vLLM: not running, 0 MiB.
- Total used: 3,059 MiB; free: 45,453 MiB.
- Both TEIs were assigned GPU 0 through NVIDIA runtime and
  `CUDA_VISIBLE_DEVICES=0`.

This proves TEI/TEI sharing. It does not measure combined TEI/vLLM contention.
GPU memory after vLLM model load, KV-cache allocation, CUDA graphs and warm-up
is unknown.

Safe repeatable capture:

```bash
nvidia-smi \
  --query-gpu=timestamp,name,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,power.draw \
  --format=csv
nvidia-smi \
  --query-compute-apps=pid,process_name,used_memory \
  --format=csv
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Command}}'
```

These commands print no application credentials.

## TEI 1.9.3

Both running containers use
`ghcr.io/huggingface/text-embeddings-inference:cuda-1.9`. The locally inspected
binary reports version 1.9.3. The immutable image digest should be captured
with `docker image inspect` before every experiment; the human-friendly tag
alone is mutable.

### Effective commands

Embedding:

```text
text-embeddings-router --model-id /app/models/models--jinaai--jina-embeddings-v5-text-small-retrieval --max-client-batch-size 50 --max-concurrent-requests 100
```

Reranker:

```text
text-embeddings-router --model-id /app/models/BAAI--bge-reranker-v2-m3 --max-client-batch-size 50 --max-concurrent-requests 100
```

Both publish container port 80. Host ports are 7997 for embedding and 7998 for
reranking. Both use Docker bridge networking, restart policy `no`, one shared
read-only conceptual model tree mounted at `/app/models`, and no Docker
healthcheck.

### Effective `/info`

| Setting | Embedding | Reranker |
|---|---:|---:|
| Architecture/type | embedding | reranker |
| `dtype` | float16 | float16 |
| Pooling | last-token | not applicable |
| `max_concurrent_requests` | 100 | 100 |
| `max_client_batch_size` | 50 | 50 |
| `max_batch_tokens` | 16,384 | 16,384 |
| `max_batch_requests` | unset (`null`) | unset (`null`) |
| `max_input_length` | 16,384 | 8,192 |
| `auto_truncate` | true | true |
| Tokenization workers | 31 | 31 |

The exact 1.9.3 `--help` confirmed support for:
`--max-concurrent-requests`, `--max-client-batch-size`,
`--max-batch-requests`, `--max-batch-tokens`, `--max-input-length`,
`--auto-truncate`, `--pooling`, `--dtype`, and
`--tokenization-workers`. Do not use flags from newer TEI documentation without
rechecking this binary.

### Initial position

Keep the current values for the first application baseline. They are known to
start, but are not proven optimal:

```text
max_concurrent_requests=100
max_client_batch_size=50
max_batch_tokens=16384
max_batch_requests=unset
auto_truncate=true
dtype=float16
tokenization_workers=31
```

Do not override embedding pooling. The live model resolved to last-token
pooling, and the application’s measured policy uses `prompt_name="query"` for
queries but raw normalized text for stored documents
(`utils/tei_embedding_client.py:14-41,81-143`). A pooling or prompt-policy
change requires a new compatible collection and retrieval-quality comparison.

Server experiments:

- `max_concurrent_requests`: test 32, 64, 100, one value per run. Lower values
  can expose overload earlier; higher admission is not guaranteed to reduce
  latency on one GPU.
- `max_batch_tokens`: test 8,192 then 16,384. Consider a higher value only if
  1.9.3 accepts it, VRAM headroom is measured, and isolated batching data shows
  a benefit.
- Keep `max_client_batch_size=50` while talk-path experiments run. It affects
  multi-input client requests, especially insertion; a single query embed is
  not a 50-item batch.
- Leave `max_batch_requests` unset initially.
- Keep `auto_truncate=true` only with explicit input-length monitoring.
  Truncation avoids rejection but can silently remove meaning.
- Keep model-selected pooling and float16 until a quality-controlled experiment
  justifies a change.
- Leave tokenization workers at observed 31 unless CPU/tokenization metrics
  identify a bottleneck.

### Health and metrics

```bash
curl -fsS --max-time 3 http://127.0.0.1:7997/health
curl -fsS --max-time 3 http://127.0.0.1:7998/health
curl -fsS --max-time 3 http://127.0.0.1:7997/info | jq \
  '{version,dtype,model_id,max_concurrent_requests,max_input_length,max_batch_tokens,max_batch_requests,max_client_batch_size,auto_truncate,tokenization_workers,model_type}'
curl -fsS --max-time 3 http://127.0.0.1:7998/info | jq \
  '{version,dtype,model_id,max_concurrent_requests,max_input_length,max_batch_tokens,max_batch_requests,max_client_batch_size,auto_truncate,tokenization_workers,model_type}'
curl -fsS --max-time 3 http://127.0.0.1:7997/metrics
curl -fsS --max-time 3 http://127.0.0.1:7998/metrics
```

The embedding endpoint exposed `te_request_*`, `te_embed_*`,
`te_queue_size`, and next-batch metrics. The reranker returned no metric
families while idle; verify after a synthetic warm-up before declaring metrics
unavailable.

### Reviewed recreation and rollback pattern

Changing TEI flags requires container recreation. First capture an immutable
rollback record:

```bash
mkdir -p /tmp/ragbot-tei-rollback
docker inspect tei-embedding > /tmp/ragbot-tei-rollback/tei-embedding.inspect.json
docker inspect tei-reranker > /tmp/ragbot-tei-rollback/tei-reranker.inspect.json
docker image inspect ghcr.io/huggingface/text-embeddings-inference:cuda-1.9 \
  > /tmp/ragbot-tei-rollback/tei-image.inspect.json
```

Then change only one container flag. Example for embedding concurrency 64:

```bash
docker stop tei-embedding
docker rename tei-embedding tei-embedding-baseline
docker run -d \
  --name tei-embedding \
  --runtime=nvidia \
  --env NVIDIA_VISIBLE_DEVICES=all \
  --env CUDA_VISIBLE_DEVICES=0 \
  --publish 7997:80 \
  --volume /root/models:/app/models \
  ghcr.io/huggingface/text-embeddings-inference:cuda-1.9 \
  --model-id /app/models/models--jinaai--jina-embeddings-v5-text-small-retrieval \
  --max-client-batch-size 50 \
  --max-concurrent-requests 64
```

Rollback that exact experiment:

```bash
docker stop tei-embedding
docker rm tei-embedding
docker rename tei-embedding-baseline tei-embedding
docker start tei-embedding
curl -fsS --max-time 3 http://127.0.0.1:7997/health
```

The same pattern applies to `tei-reranker` on host port 7998 with its observed
model path. Review these state-changing commands before execution. Do not run
two containers with the same published port.

## vLLM 0.26.0

No vLLM process/container was running, so there is no current effective model,
command, VRAM allocation, scheduler capacity, queue behavior or maximum active
request count. The locally installed `vllm/vllm-openai:latest` image identifies
vLLM 0.26.0. Because `latest` is mutable, capture and use its immutable digest
for experiments.

The installed 0.26.0 `vllm serve --help=all` verified support for:

- `--gpu-memory-utilization`
- `--max-model-len`
- `--max-num-seqs`
- `--max-num-batched-tokens`
- `--enable-prefix-caching` / `--no-enable-prefix-caching`
- `--enable-chunked-prefill` / `--no-enable-chunked-prefill`
- `--dtype`
- `--quantization`
- `--enforce-eager` / `--no-enforce-eager`
- `--tensor-parallel-size`
- `--pipeline-parallel-size`
- `--scheduler-cls`
- `--scheduling-policy` (`fcfs` or `priority`)
- `--async-scheduling`

Verified defaults include dtype `auto`, quantization `None`/model-config,
eager mode false, tensor and pipeline parallel size 1, scheduling policy
`fcfs`, and model-derived `max_model_len`. Several scheduler fields default to
automatic/model-dependent resolution; record `/metrics`, logs and the complete
launched command rather than treating a CLI `None` as the engine’s resolved
number.

### Baseline position

The following are defensible starting principles, not final numbers:

| Flag | Initial position | Reason |
|---|---|---|
| `tensor_parallel_size` | 1 | One physical GPU |
| `pipeline_parallel_size` | 1 | One physical GPU |
| `dtype` | `auto` | Respect model config until quality/memory evidence supports an override |
| `quantization` | model config / none | Quantization is model- and quality-sensitive |
| `enforce_eager` | false | Preserve CUDA graph/hybrid execution; eager is a diagnostic experiment |
| `max_model_len` | derive from measured prompt + output need | A generic large context reserves KV capacity and can reduce concurrency |
| `gpu_memory_utilization` | unknown; measure after both TEIs are warm | The historical 0.75 is not current proof and shared-GPU headroom matters |
| `max_num_seqs` | unknown; bracket observed saturation | Historical 100 is not current proof |
| `max_num_batched_tokens` | unknown; one-variable sweep | Model/prompt and vLLM-version dependent |
| Prefix caching | capture resolved current/default, then A/B | Can help repeated system/context prefixes; consumes cache memory |
| Chunked prefill | capture resolved current/default, then A/B | Can improve fairness but changes scheduling and TTFT |
| Scheduler | default class, FCFS | Custom scheduler is unsupported as a first tuning step |

Do not copy the old `gpu_memory_utilization=0.75`,
`max_num_seqs=100`, `max_model_len=4000`, or FP8 KV-cache choices from
`previous-async-tei-proposal.txt` into production. They are historical
hypotheses with no current process fingerprint.

### Required capture before first vLLM experiment

```bash
docker image inspect vllm/vllm-openai:latest \
  --format '{{json .RepoDigests}}'
docker ps --no-trunc --filter name=vllm \
  --format '{{.ID}} {{.Image}} {{.Command}}'
curl -fsS --max-time 3 http://127.0.0.1:8000/health
curl -fsS --max-time 3 http://127.0.0.1:8000/v1/models | jq \
  '{object, model_ids: [.data[].id]}'
curl -fsS --max-time 3 http://127.0.0.1:8000/metrics
```

Do not start vLLM until the staging owner confirms the intended model path and
the complete historical/current service command. A safe command template is:

```bash
docker run -d \
  --name ragbot-vllm-experiment \
  --runtime=nvidia \
  --env NVIDIA_VISIBLE_DEVICES=all \
  --ipc=host \
  --shm-size=16g \
  --publish 8000:8000 \
  --volume '<VERIFIED_HOST_MODEL_DIRECTORY>:/app/model:ro' \
  '<IMMUTABLE_VLLM_IMAGE_DIGEST>' \
  /app/model \
  --tensor-parallel-size 1 \
  --pipeline-parallel-size 1 \
  --max-model-len '<MEASURED_CONTEXT_BASELINE>' \
  --max-num-seqs '<EXPERIMENT_VALUE>' \
  --gpu-memory-utilization '<MEASURED_SAFE_VALUE>'
```

The placeholders are deliberate blockers against inventing an effective model
or memory budget. Rollback an experimental container:

```bash
docker stop ragbot-vllm-experiment
docker rm ragbot-vllm-experiment
```

If a prior vLLM container is preserved under a baseline name, restore it with
the same stop/remove/rename/start sequence used for TEI and recheck `/health`
and `/v1/models`.

## Metrics required for model-server decisions

Capture vLLM request running/waiting counts, queue time, TTFT, prefill time,
decode time, prompt/generation token throughput, KV-cache usage and
preemptions. Capture TEI request/queue/inference duration, queue depth and batch
tokens. Sample GPU utilization/memory/power at one-second intervals. Compare:

1. vLLM alone.
2. Embedding TEI alone.
3. Reranker TEI alone.
4. Both TEIs together.
5. vLLM with embedding traffic.
6. vLLM with reranking traffic.
7. Full talk workload.

Never infer combined capacity by adding isolated throughput figures.

## External settings missing from `.env`

Every vLLM and TEI server flag in this document is absent from `.env` because
the repository has no consumer for it. This includes model paths, model-server
ports, GPU memory utilization, context length, scheduler limits, prefix
caching, chunked prefill, dtype, quantization, eager execution, tensor/pipeline
parallelism, TEI server concurrency, server batching, input length,
auto-truncation, pooling and tokenizer workers. Keep them in the actual
container/service definition once that deployment source exists.
