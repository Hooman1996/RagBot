# Current intent-classifier audit

Audit date: 2026-08-10. This is a read-only audit of `intent_classifier.py` and `chitchat_guardrail.pt`; neither file was modified.

## Architecture and labels

| Item | Verified behavior |
|---|---|
| Model | PyTorch `_GuardrailNet`, a feed-forward MLP |
| Input | One 1,024-dimensional `float32` embedding per utterance |
| Layers | `Linear(1024,512)` → `BatchNorm1d(512)` → GELU → dropout 0.2 → `Linear(512,128)` → `BatchNorm1d(128)` → GELU → dropout 0.4 → `Linear(128,32)` → `BatchNorm1d(32)` → GELU → dropout 0.4 → `Linear(32,2)` |
| Pooling | None inside the classifier; pooling is owned by the external embedding model/service |
| Labels/logits | Logit 0 = `ACTIONABLE_INTENT` = banking/in-scope; logit 1 = `CHIT-CHAT` = chit-chat/non-banking/out-of-scope |
| Inference activation | `torch.softmax(logits, dim=1)` |
| Decision | Label 1 only when `p_chitchat >= 0.875`; lower-confidence/ambiguous predictions take the safer banking/RAG route. |
| `similarity_threshold` | Active constructor threshold, validated to be between zero and one; default `0.875` from held-out validation analysis |
| Loss implied by architecture | Two logits intended for cross-entropy; inference does not use sigmoid |

## Text preprocessing and embeddings

`IntentClassifier` performs no Persian normalization, tokenization, truncation, padding, or direct transformer inference. It passes the raw non-empty query unchanged to the injected asynchronous `embedding_model` callable, converts the returned sequence to a NumPy `float32` array, and requires exact shape `(1024,)`. Empty/whitespace input bypasses embedding and routes to label 0.

Consequently, tokenizer type, maximum sequence length, token-level pooling, and any internal embedding normalization are not defined by `intent_classifier.py`; they are properties of the injected embedding service. The currently verified startup path in `main.py` injects `rag_system.search_engine._encode_query`. That calls the shared TEI client with:

```json
{"inputs": "<raw query>", "prompt_name": "query", "normalize": true}
```

The TEI model performs tokenization, truncation, and pooling outside this repository process. No application-side maximum sequence length was found.

There is a material contract discrepancy to resolve with evaluation evidence: the checkpoint metadata says `jina_task = "classification"` and names an old local Jina model path, while the current live callable uses the retrieval model's `prompt_name="query"` policy. The offline pipeline defaults to `live-query` because that reproduces the verified current inference path. It also exposes `checkpoint-classification`, but training must not use that option unless the deployed TEI endpoint proves that prompt/adapter exists and returns the required 1,024-dimensional embeddings.

## Checkpoint format

`chitchat_guardrail.pt` is a trainable, safe-loadable checkpoint dictionary—not a serialized complete module. `torch.load(..., weights_only=True)` returned:

- `model_state_dict`: 23 tensors/buffers matching the MLP exactly;
- `input_dim`: `1024`;
- `jina_model`: a historical local model path;
- `jina_task`: `classification`;
- `label_map`: `{0: "ACTIONABLE_INTENT", 1: "CHIT-CHAT"}`.

It contains no optimizer state, scheduler state, epoch, or training-history metadata. Strict loading reported no missing or unexpected keys. The output weight has shape `(2, 32)`. The verified original SHA256 is:

`c1f55e9bd4c67764d10052ac45d8c34285329f56047bde7a48c0a7f6b8ae49cc`

The loader accepts `model_state_dict`, the legacy `model_state` key, or a bare state dictionary. The new trainer writes the preferred five-key dictionary above and saves only tensors/scalars/strings/maps, so `weights_only=True` remains compatible.

## Device and runtime behavior

- An explicit constructor `device` is honored; otherwise CUDA is selected when `torch.cuda.is_available()`, with CPU fallback.
- The model is moved to the selected device and placed in evaluation mode.
- Inference creates a `(1, 1024)` tensor and runs under `torch.no_grad()` and an in-process lock.
- Blocking Torch work is normally sent through `asyncio.to_thread`; an injected `blocking_runner` is also supported.
- Missing checkpoints do not fail closed: the code prints a warning but leaves a randomly initialized network despite the warning text saying all queries route to RAG. Production should therefore always verify checkpoint presence and strict compatibility before startup.

## Path configuration and compatible activation

The default relative path now selects `chitchat_guardrail_finetuned.pt`. `IntentClassifier(..., classifier_model_path=<path>)` also supports an alternate file. `main.py` relies on this default and no verified environment-variable setting selects a different checkpoint.

A compatible new checkpoint must load strictly into `_GuardrailNet`, retain 1,024 input features and two ordered logits, and expose label 0/1 as above. Offline activation can use the existing constructor parameter immediately. A later controlled application change may pass the new path explicitly; no checkpoint replacement or deployment is performed by this work.
