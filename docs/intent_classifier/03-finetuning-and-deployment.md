# Fine-tuning, evaluation, and deployment safety

This pipeline is offline-only. It does not modify the application, live `.env`, FAQ chunks, original checkpoint, or deployed model selection.

## 1. Generate and inspect the dataset

Use the repository's Python 3.12 environment:

```bash
/root/miniconda3/envs/faq/bin/python3.12 training/intent_classifier/build_training_dataset.py --seed 42
```

Inspect `training/intent_classifier/reports/dataset_summary.md`, sample each `example_type`, and review `training/intent_classifier/data/review_required.csv`. Rows in the review file are excluded. The builder reads every visible, non-empty `.txt` FAQ chunk, never writes answers, removes duplicates, assigns intact groups with seed 42, and creates separate train/validation/test/adversarial files.

Run the integrity and compatibility tests:

```bash
/root/miniconda3/envs/faq/bin/python3.12 -m unittest discover -s tests/intent_classifier -v
```

Before any embedding or training work, run the non-mutating gate:

```bash
/root/miniconda3/envs/faq/bin/python3.12 training/intent_classifier/train_intent_classifier.py --preflight-only --seed 42
```

## 2. Embedding contract

The default `--embedding-policy live-query` reproduces the currently verified application callable: normalized TEI embeddings with `prompt_name="query"`. Export `TEI_EMBED_URL` in the shell or pass `--tei-url`; the script does not parse credentials from source or `.env`. Embeddings are cached periodically under the ignored `training/intent_classifier/cache/` directory, making interrupted runs resumable with at most 99 batches repeated.

Do not select `--embedding-policy checkpoint-classification` merely because the old checkpoint contains that metadata. First prove the staging TEI image/model supports `prompt_name="classification"`, produces 1,024 finite values, and matches the intended Jina adapter. The preflight request fails rather than silently falling back.

## 3. Train safely

The defaults are documented and reproducible: seed 42, batch size 256, AdamW, learning rate `1e-4`, weight decay `1e-2`, gradient clipping at 1.0, cosine decay to 10% of the initial rate, at most 20 epochs, validation macro-F1 selection with a 0.97 banking-recall floor, and early stopping after four unimproved epochs.

Only after confirming the staging GPU is not serving inference or another workload, run:

```bash
TEI_EMBED_URL=<staging-tei-base-url> /root/miniconda3/envs/faq/bin/python3.12 training/intent_classifier/train_intent_classifier.py \
  --train-csv training/intent_classifier/data/intent_classifier_train.csv \
  --validation-csv training/intent_classifier/data/intent_classifier_validation.csv \
  --test-csv training/intent_classifier/data/intent_classifier_test.csv \
  --adversarial-csv training/intent_classifier/data/intent_classifier_adversarial_test.csv \
  --initial-checkpoint /root/projects/faq/chitchat_guardrail.pt \
  --output-checkpoint /root/projects/faq/chitchat_guardrail_finetuned.pt \
  --embedding-policy live-query \
  --device cuda \
  --seed 42 \
  --confirm-resource-safe
```

The trainer refuses to overwrite either the original checkpoint or an existing output, saves a timestamped copy under `training/intent_classifier/checkpoints/`, re-loads the result strictly, checks the original SHA256 again, and evaluates old/new checkpoints on identical validation, test, and adversarial examples.

The final recorded run used the port-7997 TEI service for normalized `prompt_name="query"` embeddings and performed MLP optimization on CPU, after the user explicitly authorized fine-tuning. It completed at epoch 14 via early stopping and produced `/root/projects/faq/chitchat_guardrail_finetuned.pt`. See `training_status.md` and `model_comparison.md` for the measured results.

## 4. Evaluate and compare

After training, run the standalone same-set comparison:

```bash
TEI_EMBED_URL=<staging-tei-base-url> /root/miniconda3/envs/faq/bin/python3.12 training/intent_classifier/evaluate_intent_classifier.py \
  --old-checkpoint /root/projects/faq/chitchat_guardrail.pt \
  --new-checkpoint /root/projects/faq/chitchat_guardrail_finetuned.pt \
  --embedding-policy live-query \
  --device cuda
```

The reports include overall and macro metrics, per-class metrics, confusion matrices, banking-to-chitchat and non-banking-to-banking errors, difficulty/type subgroups, threshold sweep, and adversarial performance. Threshold recommendations are offline evidence only; `intent_classifier.py` remains unchanged.

Do not recommend deployment unless the new model meaningfully improves held-out hard-negative, hard-positive, and adversarial performance without a serious banking-recall regression. Also run the repository's retrieval and answer-quality suites before any model-behavior deployment; their canonical commands are currently unknown, so their absence is a deployment blocker rather than permission to skip them.

## 5. Offline compatibility test

The constructor already supports a model path. An offline process can load the new weights without changing application source:

```python
classifier = IntentClassifier(
    embedding_model=the_same_async_live_query_embedding_callable,
    classifier_model_path="/root/projects/faq/chitchat_guardrail_finetuned.pt",
    device="cpu",
)
```

The automated new-checkpoint tests become active as soon as that file exists and verify strict keys, two-logit output, label ordering, and the public preprocessing/inference path.

## 6. Activation and rollback

The application default in `intent_classifier.py` now selects:

```python
classifier_model_path="chitchat_guardrail_finetuned.pt"
```

The classifier now actively uses the validation-selected `p_chitchat=0.875` threshold. Predictions below that threshold take the safer banking/RAG route. The threshold remains constructor-configurable for controlled evaluation and rollback.

The running Uvicorn development server detected the source update and reloaded its worker. For a managed staging deployment, restart the application service explicitly, then run smoke/quality tests and monitor both routing-error directions. Production infrastructure is out of scope.

Rollback is a one-line source change restoring the constructor default to `chitchat_guardrail.pt`, followed by a staging restart and verification of the original SHA256:

```bash
sha256sum /root/projects/faq/chitchat_guardrail.pt
```

Expected original checksum:

`c1f55e9bd4c67764d10052ac45d8c34285329f56047bde7a48c0a7f6b8ae49cc`

Record the new checksum from `training_config.json` and the evaluation report after a real training run. No new checksum exists until the gated run completes.
