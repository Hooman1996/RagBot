#!/usr/bin/env python3
"""Evaluate compatible old/new guardrail checkpoints on identical held-out sets."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import torch

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.intent_classifier.common import dump_json, read_csv
from training.intent_classifier.embedding_io import embed_texts
from training.intent_classifier.modeling import (
    evaluate_rows,
    load_compatible_checkpoint,
    predict_probabilities,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "training/intent_classifier/data"
REPORTS = ROOT / "training/intent_classifier/reports"


def threshold_sweep(rows: list[dict[str, str]], probabilities: np.ndarray) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    thresholds = sorted(set(np.round(np.arange(0.05, 0.951, 0.025), 3).tolist() + [0.96, 0.97, 0.975, 0.98, 0.985, 0.99, 0.995]))
    for threshold in thresholds:
        metrics = evaluate_rows(rows, probabilities, float(threshold))
        banking = metrics["per_class"]["banking"]
        nonbanking = metrics["per_class"]["chitchat_nonbanking"]
        output.append({
            "threshold_p_chitchat": float(threshold),
            "banking_recall": banking["recall"], "banking_precision": banking["precision"],
            "chitchat_recall": nonbanking["recall"], "chitchat_precision": nonbanking["precision"],
            "macro_f1": metrics["macro_f1"],
            "banking_misrouted_to_chitchat_rate": metrics["banking_misrouted_to_chitchat_rate"],
            "nonbanking_misrouted_to_banking_rate": metrics["nonbanking_misrouted_to_banking_rate"],
        })
    return output


def recommend_threshold(rows: list[dict[str, Any]], min_banking_recall: float, min_nonbanking_recall: float) -> dict[str, Any]:
    eligible = [row for row in rows if row["banking_recall"] >= min_banking_recall and row["chitchat_recall"] >= min_nonbanking_recall]
    candidates = eligible or rows
    recommended = max(candidates, key=lambda row: (row["macro_f1"], row["banking_recall"], -abs(row["threshold_p_chitchat"] - 0.5)))
    return {
        "selection_constraints_met": bool(eligible),
        "minimum_banking_recall": min_banking_recall,
        "minimum_chitchat_recall": min_nonbanking_recall,
        "recommended": recommended,
        "note": "Recommendation is offline only; intent_classifier.py is not modified.",
    }


def write_threshold_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def evaluate_checkpoint(
    name: str, checkpoint: Path, datasets: dict[str, list[dict[str, str]]],
    embeddings: dict[str, np.ndarray], device: torch.device, batch_size: int,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    model, payload = load_compatible_checkpoint(checkpoint, device)
    metrics: dict[str, Any] = {
        "checkpoint": str(checkpoint), "sha256": sha256_file(checkpoint),
        "checkpoint_jina_task": payload.get("jina_task"), "label_map": payload.get("label_map"),
    }
    probabilities: dict[str, np.ndarray] = {}
    for split, rows in datasets.items():
        probabilities[split] = predict_probabilities(model, embeddings[split], device, batch_size)
        metrics[split] = evaluate_rows(rows, probabilities[split])
    return metrics, probabilities


def comparison_markdown(results: dict[str, Any]) -> str:
    names = list(results)
    lines = ["# Old/new intent-classifier comparison", "", "Label 0 is banking/in-scope; label 1 is chit-chat/non-banking/out-of-scope.", ""]
    lines.extend(["| Checkpoint | Set | Accuracy | Macro F1 | Banking recall | Chit-chat recall | Banking → chit-chat | Non-banking → banking |", "|---|---|---:|---:|---:|---:|---:|---:|"])
    for name in names:
        for split in ("validation", "test", "adversarial"):
            metric = results[name][split]
            lines.append(
                f"| {name} | {split} | {metric['accuracy']:.4f} | {metric['macro_f1']:.4f} | "
                f"{metric['banking_recall']:.4f} | {metric['chitchat_recall']:.4f} | "
                f"{metric['banking_misrouted_to_chitchat']} | {metric['nonbanking_misrouted_to_banking']} |"
            )
    lines.extend(["", "Deployment recommendation is intentionally deferred until both checkpoints have complete held-out and adversarial results and the new model has no serious banking-recall regression.", ""])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-csv", type=Path, default=DATA / "intent_classifier_validation.csv")
    parser.add_argument("--test-csv", type=Path, default=DATA / "intent_classifier_test.csv")
    parser.add_argument("--adversarial-csv", type=Path, default=DATA / "intent_classifier_adversarial_test.csv")
    parser.add_argument("--old-checkpoint", type=Path, default=ROOT / "chitchat_guardrail.pt")
    parser.add_argument("--new-checkpoint", type=Path, default=None)
    parser.add_argument("--embedding-cache", type=Path, default=ROOT / "training/intent_classifier/cache/evaluation_embeddings.npz")
    parser.add_argument("--tei-url", default=None)
    parser.add_argument("--tei-request-concurrency", type=int, default=16)
    parser.add_argument("--inference-batch-size", type=int, default=1024)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--reports-dir", type=Path, default=REPORTS)
    parser.add_argument("--minimum-banking-recall", type=float, default=0.97)
    parser.add_argument("--minimum-chitchat-recall", type=float, default=0.85)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = torch.device("cuda" if args.device == "auto" and torch.cuda.is_available() else ("cpu" if args.device == "auto" else args.device))
    datasets = {
        "validation": read_csv(args.validation_csv), "test": read_csv(args.test_csv),
        "adversarial": read_csv(args.adversarial_csv),
    }
    all_texts = [row["text"] for rows in datasets.values() for row in rows]
    dataset_fingerprint = hashlib.sha256(
        "\n".join(all_texts).encode("utf-8")
    ).hexdigest()
    all_embeddings = embed_texts(
        all_texts,
        cache_path=args.embedding_cache,
        dataset_fingerprint=dataset_fingerprint,
        tei_url=args.tei_url,
        request_concurrency=args.tei_request_concurrency,
    )
    embeddings: dict[str, np.ndarray] = {}
    offset = 0
    for split, rows in datasets.items():
        embeddings[split] = all_embeddings[offset : offset + len(rows)]
        offset += len(rows)

    checkpoints = {"old": args.old_checkpoint}
    if args.new_checkpoint:
        checkpoints["new"] = args.new_checkpoint
    results: dict[str, Any] = {}
    validation_probabilities: dict[str, np.ndarray] = {}
    all_probabilities: dict[str, dict[str, np.ndarray]] = {}
    for name, checkpoint in checkpoints.items():
        results[name], probabilities = evaluate_checkpoint(name, checkpoint, datasets, embeddings, device, args.inference_batch_size)
        validation_probabilities[name] = probabilities["validation"]
        all_probabilities[name] = probabilities
        for split in datasets:
            dump_json(args.reports_dir / f"{name}_{split}_metrics.json", results[name][split])

    threshold_rows = threshold_sweep(datasets["validation"], validation_probabilities["new" if "new" in results else "old"])
    write_threshold_csv(args.reports_dir / "threshold_analysis.csv", threshold_rows)
    recommendation = recommend_threshold(threshold_rows, args.minimum_banking_recall, args.minimum_chitchat_recall)
    dump_json(args.reports_dir / "threshold_recommendation.json", recommendation)
    selected_name = "new" if "new" in results else "old"
    selected_threshold = float(recommendation["recommended"]["threshold_p_chitchat"])
    dump_json(args.reports_dir / "recommended_threshold_metrics.json", {
        "checkpoint": selected_name,
        "threshold_p_chitchat": selected_threshold,
        **{
            split: evaluate_rows(rows, all_probabilities[selected_name][split], selected_threshold)
            for split, rows in datasets.items()
        },
    })
    dump_json(args.reports_dir / "model_comparison.json", results)
    (args.reports_dir / "model_comparison.md").write_text(comparison_markdown(results), encoding="utf-8")
    print(f"Evaluation complete on {device}; reports: {args.reports_dir}")


if __name__ == "__main__":
    main()
