#!/usr/bin/env python3
"""Train the authoritative intent MLP on live retrieval-query embeddings."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from dotenv import load_dotenv
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from intent_classifier import (
    EXPECTED_ARCHITECTURE,
    EXPECTED_EMBEDDING_PROMPT,
    EXPECTED_EMBEDDING_ROLE,
    EXPECTED_LABEL_MAP,
    JINA_DIM,
    _GuardrailNet,
)
from training.intent_classifier.common import (
    classification_metrics,
    dump_json,
    read_csv,
)
from training.intent_classifier.embedding_io import (
    EMBEDDING_POLICY,
    embed_texts,
    resolve_tei_url,
    tei_endpoint_identity,
)
from training.intent_classifier.modeling import predict_probabilities, sha256_file
from utils.persian_normalization import normalize_persian_text


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "training/intent_classifier"
DEFAULT_ARTIFACT = (
    ROOT / "training/artifacts/intent_guardrail_jina_retrieval_query_v1.pt"
)
DEFAULT_REPORT = (
    ROOT
    / "training/artifacts/intent_guardrail_jina_retrieval_query_v1_metrics.json"
)
DEFAULT_CACHE = (
    ROOT
    / "training/artifacts/intent_guardrail_jina_retrieval_query_v1_embeddings.npz"
)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True


def audit_and_deduplicate(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    exact_counts: Counter[str] = Counter()
    empty_rows = 0
    invalid_labels = 0
    for row in rows:
        text = row.get("text", "")
        label = row.get("label", "")
        if not text.strip():
            empty_rows += 1
            continue
        if label not in {"0", "1"}:
            invalid_labels += 1
            continue
        canonical = normalize_persian_text(text)
        if not canonical:
            empty_rows += 1
            continue
        groups[canonical].append(row)
        exact_counts[text] += 1

    clean: list[dict[str, str]] = []
    conflicting_groups = 0
    duplicate_groups = 0
    duplicate_rows_removed = 0
    conflicting_samples = 0
    existing_split_leakage_groups = 0
    for canonical in sorted(groups):
        group = groups[canonical]
        labels = {row["label"] for row in group}
        if len(labels) > 1:
            conflicting_groups += 1
            conflicting_samples += len(group)
            continue
        if len({row.get("split", "") for row in group}) > 1:
            existing_split_leakage_groups += 1
        if len(group) > 1:
            duplicate_groups += 1
            duplicate_rows_removed += len(group) - 1
        selected = dict(group[0])
        selected["canonical_query"] = canonical
        clean.append(selected)
    audit = {
        "source_rows": len(rows),
        "empty_rows_excluded": empty_rows,
        "invalid_label_rows_excluded": invalid_labels,
        "exact_duplicate_groups": sum(count > 1 for count in exact_counts.values()),
        "exact_duplicate_rows": sum(
            count - 1 for count in exact_counts.values() if count > 1
        ),
        "normalized_duplicate_groups": duplicate_groups,
        "normalized_duplicate_rows_removed": duplicate_rows_removed,
        "conflicting_normalized_groups_excluded": conflicting_groups,
        "conflicting_normalized_samples_excluded": conflicting_samples,
        "existing_split_normalized_leakage_groups": (
            existing_split_leakage_groups
        ),
        "clean_rows": len(clean),
    }
    return clean, audit


def deterministic_stratified_split(
    rows: list[dict[str, str]], seed: int
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    splits: dict[str, list[dict[str, str]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for label in (0, 1):
        label_rows = sorted(
            (row for row in rows if int(row["label"]) == label),
            key=lambda row: row["canonical_query"],
        )
        random.Random(seed + label).shuffle(label_rows)
        count = len(label_rows)
        validation_count = round(count * 0.10)
        test_count = round(count * 0.10)
        train_count = count - validation_count - test_count
        allocations = (
            ("train", label_rows[:train_count]),
            (
                "validation",
                label_rows[train_count : train_count + validation_count],
            ),
            ("test", label_rows[train_count + validation_count :]),
        )
        for split_name, allocated in allocations:
            for row in allocated:
                row["split"] = split_name
            splits[split_name].extend(allocated)
    for offset, split_name in enumerate(("train", "validation", "test")):
        random.Random(seed + 100 + offset).shuffle(splits[split_name])
    canonical_sets = {
        name: {row["canonical_query"] for row in split_rows}
        for name, split_rows in splits.items()
    }
    if (
        canonical_sets["train"] & canonical_sets["validation"]
        or canonical_sets["train"] & canonical_sets["test"]
        or canonical_sets["validation"] & canonical_sets["test"]
    ):
        raise ValueError("Canonical query leakage across splits")
    return splits["train"], splits["validation"], splits["test"]


def select_splits(
    rows: list[dict[str, str]], audit: dict[str, int], seed: int
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    str,
]:
    valid_names = {"train", "validation", "test"}
    split_names = {row.get("split", "") for row in rows}
    counts = Counter(row.get("split", "") for row in rows)
    per_split_labels = {
        name: {int(row["label"]) for row in rows if row.get("split") == name}
        for name in valid_names
    }
    existing_valid = (
        split_names == valid_names
        and all(counts[name] > 0 for name in valid_names)
        and all(labels == {0, 1} for labels in per_split_labels.values())
        and audit["existing_split_normalized_leakage_groups"] == 0
    )
    if existing_valid:
        return (
            [row for row in rows if row["split"] == "train"],
            [row for row in rows if row["split"] == "validation"],
            [row for row in rows if row["split"] == "test"],
            "existing_leakage_free_split",
        )
    train_rows, validation_rows, test_rows = deterministic_stratified_split(
        rows, seed
    )
    return train_rows, validation_rows, test_rows, "seeded_80_10_10_split"


def fingerprint_dataset(rows: list[dict[str, str]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: item["canonical_query"]):
        digest.update(row["canonical_query"].encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(str(int(row["label"])).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def evaluate_probabilities(
    rows: list[dict[str, str]], probabilities: np.ndarray, threshold: float
) -> dict[str, Any]:
    predictions = (probabilities[:, 1] >= threshold).astype(np.int64)
    metrics = classification_metrics(
        [int(row["label"]) for row in rows], predictions
    )
    metrics["threshold"] = float(threshold)
    metrics["actionable"] = metrics["per_class"]["banking"]
    metrics["chitchat"] = metrics["per_class"]["chitchat_nonbanking"]
    return metrics


def select_threshold(
    rows: list[dict[str, str]], probabilities: np.ndarray
) -> tuple[float, dict[str, Any], bool]:
    values = probabilities[:, 1].astype(np.float64)
    candidates = np.unique(
        np.concatenate(
            (
                values,
                np.asarray([0.5, np.nextafter(1.0, 0.0)], dtype=np.float64),
            )
        )
    )
    evaluated = [
        (float(threshold), evaluate_probabilities(rows, probabilities, threshold))
        for threshold in candidates
        if 0.0 < threshold < 1.0
    ]
    eligible = [item for item in evaluated if item[1]["actionable"]["recall"] >= 0.99]
    pool = eligible or evaluated
    if eligible:
        chosen = max(
            pool,
            key=lambda item: (
                round(item[1]["macro_f1"], 12),
                item[0],
            ),
        )
    else:
        chosen = max(
            pool,
            key=lambda item: (
                item[1]["actionable"]["recall"],
                round(item[1]["macro_f1"], 12),
                item[0],
            ),
        )
    return chosen[0], chosen[1], bool(eligible)


def _selection_key(metrics: dict[str, Any], constraint_met: bool) -> tuple:
    return (
        int(constraint_met),
        round(metrics["macro_f1"], 12),
        round(metrics["actionable"]["recall"], 12),
    )


def train(args: argparse.Namespace) -> None:
    seed_everything(args.seed)
    if args.output_checkpoint.exists() and not args.audit_only:
        raise FileExistsError(
            f"Refusing to overwrite existing checkpoint: {args.output_checkpoint}"
        )
    source_rows = read_csv(args.dataset)
    clean_rows, audit = audit_and_deduplicate(source_rows)
    train_rows, validation_rows, test_rows, split_source = select_splits(
        clean_rows, audit, args.seed
    )
    dataset_fingerprint = fingerprint_dataset(clean_rows)
    class_counts = Counter(int(row["label"]) for row in clean_rows)
    print(
        json.dumps(
            {
                "dataset_audit": audit,
                "class_counts": dict(class_counts),
                "splits": {
                    "train": len(train_rows),
                    "validation": len(validation_rows),
                    "test": len(test_rows),
                },
                "split_source": split_source,
                "dataset_fingerprint": dataset_fingerprint,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.audit_only:
        return

    train_validation_rows = train_rows + validation_rows
    train_validation_embeddings = embed_texts(
        [row["text"] for row in train_validation_rows],
        cache_path=args.embedding_cache,
        dataset_fingerprint=dataset_fingerprint,
        tei_url=args.tei_url,
        request_concurrency=args.tei_request_concurrency,
        timeout=args.tei_timeout,
    )
    train_x = train_validation_embeddings[: len(train_rows)]
    validation_x = train_validation_embeddings[len(train_rows) :]
    train_y = np.asarray([int(row["label"]) for row in train_rows], dtype=np.int64)

    device = torch.device(args.device)
    model = _GuardrailNet().to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay
    )
    loss_function = nn.CrossEntropyLoss()
    generator = torch.Generator().manual_seed(args.seed)
    loader = DataLoader(
        TensorDataset(torch.from_numpy(train_x), torch.from_numpy(train_y)),
        batch_size=args.batch_size,
        shuffle=True,
        generator=generator,
        num_workers=0,
        drop_last=False,
    )

    best_state: dict[str, torch.Tensor] | None = None
    best_key: tuple | None = None
    epochs_without_improvement = 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        loss_total = 0.0
        seen = 0
        for features, labels in loader:
            features = features.to(device)
            labels = labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_function(model(features), labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
            optimizer.step()
            loss_total += float(loss.item()) * len(labels)
            seen += len(labels)

        validation_probabilities = predict_probabilities(
            model, validation_x, device, args.inference_batch_size
        )
        threshold, validation_metrics, constraint_met = select_threshold(
            validation_rows, validation_probabilities
        )
        current_key = _selection_key(validation_metrics, constraint_met)
        history_row = {
            "epoch": epoch,
            "train_loss": loss_total / seen,
            "validation_accuracy": validation_metrics["accuracy"],
            "validation_macro_f1": validation_metrics["macro_f1"],
            "validation_actionable_recall": validation_metrics["actionable"]["recall"],
            "selected_threshold": threshold,
            "actionable_recall_constraint_met": constraint_met,
        }
        history.append(history_row)
        print(json.dumps(history_row))
        if best_key is None or current_key > best_key:
            best_key = current_key
            best_state = copy.deepcopy(model.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
        if epochs_without_improvement >= args.early_stopping_patience:
            print(f"early stopping at epoch {epoch}")
            break

    if best_state is None:
        raise RuntimeError("No model state selected")
    model.load_state_dict(best_state, strict=True)
    validation_probabilities = predict_probabilities(
        model, validation_x, device, args.inference_batch_size
    )
    selected_threshold, validation_metrics, threshold_constraint_met = (
        select_threshold(validation_rows, validation_probabilities)
    )

    # The test split is embedded and evaluated only after model and threshold freeze.
    test_x = embed_texts(
        [row["text"] for row in test_rows],
        cache_path=args.embedding_cache,
        dataset_fingerprint=dataset_fingerprint,
        tei_url=args.tei_url,
        request_concurrency=args.tei_request_concurrency,
        timeout=args.tei_timeout,
    )
    test_probabilities = predict_probabilities(
        model, test_x, device, args.inference_batch_size
    )
    test_metrics = evaluate_probabilities(
        test_rows, test_probabilities, selected_threshold
    )

    resolved_tei_url = resolve_tei_url(args.tei_url)
    training_timestamp = datetime.now(timezone.utc).isoformat()
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "label_map": EXPECTED_LABEL_MAP,
        "architecture": EXPECTED_ARCHITECTURE,
        "embedding_dimension": JINA_DIM,
        "embedding_role": EXPECTED_EMBEDDING_ROLE,
        "embedding_prompt_name": EXPECTED_EMBEDDING_PROMPT,
        "embedding_normalize": True,
        "normalizer": "normalize_persian_text",
        "training_seed": args.seed,
        "embedding_model": os.getenv("EMBEDDING_MODEL", "unknown"),
        "tei_endpoint_identity": tei_endpoint_identity(resolved_tei_url),
        "dataset_fingerprint": dataset_fingerprint,
        "training_timestamp": training_timestamp,
        "selected_threshold": selected_threshold,
        "train_size": len(train_rows),
        "validation_size": len(validation_rows),
        "test_size": len(test_rows),
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
    }
    args.output_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, args.output_checkpoint)
    checkpoint_sha256 = sha256_file(args.output_checkpoint)

    # Strict post-save compatibility check without running any external service.
    reloaded = torch.load(args.output_checkpoint, map_location="cpu", weights_only=True)
    reloaded_model = _GuardrailNet()
    reloaded_model.load_state_dict(reloaded["model_state_dict"], strict=True)
    if reloaded["label_map"] != EXPECTED_LABEL_MAP:
        raise ValueError("Saved label map changed")
    report = {
        "dataset": {
            "path": str(args.dataset),
            "audit": audit,
            "clean_class_counts": {
                "actionable": class_counts[0],
                "chitchat": class_counts[1],
            },
            "split_counts": {
                "train": len(train_rows),
                "validation": len(validation_rows),
                "test": len(test_rows),
            },
            "split_source": split_source,
            "split_class_counts": {
                split_name: dict(Counter(int(row["label"]) for row in rows))
                for split_name, rows in (
                    ("train", train_rows),
                    ("validation", validation_rows),
                    ("test", test_rows),
                )
            },
        },
        "training_seed": args.seed,
        "dataset_fingerprint": dataset_fingerprint,
        "training_timestamp": training_timestamp,
        "epochs_completed": len(history),
        "history": history,
        "selected_threshold": selected_threshold,
        "actionable_recall_constraint_met": threshold_constraint_met,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "checkpoint_path": str(args.output_checkpoint),
        "checkpoint_sha256": checkpoint_sha256,
        "embedding_policy": {
            "source": "TEI retrieval-query",
            "cache_policy": EMBEDDING_POLICY,
            "dimension": JINA_DIM,
            "role": EXPECTED_EMBEDDING_ROLE,
            "prompt_name": EXPECTED_EMBEDDING_PROMPT,
            "normalize": True,
            "normalizer": "normalize_persian_text",
            "client": "TeiEmbeddingClient.embed_query",
            "payload_builder": "build_query_payload",
            "embedding_model": os.getenv("EMBEDDING_MODEL", "unknown"),
            "tei_endpoint_identity": tei_endpoint_identity(resolved_tei_url),
        },
    }
    dump_json(args.output_report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=BASE / "data/intent_classifier_finetune.csv"
    )
    parser.add_argument("--output-checkpoint", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--embedding-cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--tei-url", default=None)
    parser.add_argument("--tei-request-concurrency", type=int, default=16)
    parser.add_argument("--tei-timeout", type=float, default=60.0)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--inference-batch-size", type=int, default=1024)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-2)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--early-stopping-patience", type=int, default=4)
    parser.add_argument("--audit-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    load_dotenv(dotenv_path=ROOT / ".env")
    train(parse_args())
