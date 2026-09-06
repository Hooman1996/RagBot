"""Shared, side-effect-free helpers for intent-classifier experiments."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


LABEL_BANKING = 0
LABEL_NONBANKING = 1
LABEL_MAP = {0: "ACTIONABLE_INTENT", 1: "CHITCHAT"}
EXPECTED_INPUT_DIM = 1024
REQUIRED_COLUMNS = (
    "text",
    "label",
    "example_type",
    "difficulty",
    "source_question_id",
    "source_question",
    "category",
    "sub_category",
    "generation_family",
    "split",
)

FAQ_PATTERN = re.compile(
    r"^question\s*:\s*(.*?)\s*\n"
    r"answer\s*:\s*(.*?)\s*\n"
    r"question category\s*:\s*(.*?)"
    r"(?:\s+sub_category\s*:\s*(.*?))?\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class FAQ:
    source_question_id: str
    question: str
    answer: str
    category: str
    sub_category: str
    source_filename: str


def normalize_persian(text: str, *, punctuation: bool = False) -> str:
    """Normalize only for comparisons; never rewrite final training text."""
    value = unicodedata.normalize("NFKC", str(text))
    value = value.translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"}))
    value = value.replace("\u200c", " ").replace("\u200f", "").replace("\ufeff", "")
    if punctuation:
        value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip().casefold()


def stable_id(prefix: str, *parts: str, length: int = 16) -> str:
    material = "\x1f".join(normalize_persian(part, punctuation=True) for part in parts)
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:length]}"


def parse_faq_file(path: Path, root: Path) -> FAQ:
    content = path.read_text(encoding="utf-8-sig").strip()
    match = FAQ_PATTERN.match(content)
    if not match:
        raise ValueError(f"Invalid FAQ chunk format: {path}")
    question, answer, category, sub_category = match.groups()
    question = question.strip()
    if not question:
        raise ValueError(f"FAQ has an empty question: {path}")
    # Identical source questions deliberately share an ID to prevent split leakage.
    source_id = stable_id("faq", question)
    return FAQ(
        source_question_id=source_id,
        question=question,
        answer=answer.strip(),
        category=category.strip(),
        sub_category=(sub_category or "").strip(),
        source_filename=str(path.relative_to(root)),
    )


def read_faqs(root: Path) -> tuple[list[FAQ], dict[str, int]]:
    """Read every valid visible, non-empty .txt chunk below ``root``."""
    faqs: list[FAQ] = []
    stats = {
        "hidden_ignored": 0,
        "empty_ignored": 0,
        "temporary_ignored": 0,
        "non_txt_ignored": 0,
    }
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in relative_parts):
            stats["hidden_ignored"] += 1
            continue
        if (
            path.name.endswith(("~", ".tmp", ".temp", ".swp"))
            or path.name.startswith("#")
        ):
            stats["temporary_ignored"] += 1
            continue
        if path.stat().st_size == 0:
            stats["empty_ignored"] += 1
            continue
        if path.suffix.lower() != ".txt":
            stats["non_txt_ignored"] += 1
            continue
        faqs.append(parse_faq_file(path, root))
    return faqs, stats


def write_csv(path: Path, rows: Sequence[dict[str, Any]], columns: Sequence[str] = REQUIRED_COLUMNS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def deduplicate_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Remove duplicates while retaining deliberate, raw-distinct typo variants."""
    kept: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    seen_raw: set[str] = set()
    removed = 0
    for row in rows:
        key = normalize_persian(str(row["text"]), punctuation=True)
        raw_key = unicodedata.normalize("NFC", str(row["text"])).strip()
        label = int(row["label"])
        if key in seen:
            if seen[key] != label:
                raise ValueError(f"Conflicting labels for normalized duplicate: {row['text']!r}")
            if row.get("example_type") == "typo_variant" and raw_key not in seen_raw:
                seen_raw.add(raw_key)
                kept.append(row)
                continue
            removed += 1
            continue
        seen[key] = label
        seen_raw.add(raw_key)
        kept.append(row)
    return kept, removed


def _allocate_groups(
    groups: dict[str, list[dict[str, Any]]], seed: int, ratios: tuple[float, float, float]
) -> dict[str, str]:
    """Greedily allocate intact groups while tracking target row counts."""
    rng = random.Random(seed)
    items = list(groups.items())
    rng.shuffle(items)
    items.sort(key=lambda item: len(item[1]), reverse=True)
    total = sum(len(rows) for _, rows in items)
    names = ("train", "validation", "test")
    targets = dict(zip(names, (total * ratio for ratio in ratios), strict=True))
    counts = dict.fromkeys(names, 0)
    assignment: dict[str, str] = {}
    for group_id, group_rows in items:
        split = max(names, key=lambda name: targets[name] - counts[name])
        assignment[group_id] = split
        counts[split] += len(group_rows)
    return assignment


def grouped_split(
    rows: list[dict[str, Any]], seed: int = 42, ratios: tuple[float, float, float] = (0.8, 0.1, 0.1)
) -> list[dict[str, Any]]:
    if not np.isclose(sum(ratios), 1.0):
        raise ValueError("Split ratios must sum to one")
    # Banking source groups contain several example types and stay intact. Label-1
    # families contain one type, so stratify those groups by type to guarantee
    # ordinary validation/test coverage of chit-chat, non-banking, and hard positives.
    strata: list[tuple[int, str | None]] = [(LABEL_BANKING, None)]
    strata.extend(
        (LABEL_NONBANKING, example_type)
        for example_type in sorted({str(row["example_type"]) for row in rows if int(row["label"]) == LABEL_NONBANKING})
    )
    for label, example_type in strata:
        label_rows = [
            row for row in rows
            if int(row["label"]) == label and (example_type is None or row["example_type"] == example_type)
        ]
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in label_rows:
            group_id = str(row["source_question_id"] or row["generation_family"])
            if not group_id:
                raise ValueError("Every row needs a source or generation-family group")
            groups[group_id].append(row)
        stratum_material = f"{label}:{example_type or 'all'}"
        stratum_seed = seed + int(hashlib.sha256(stratum_material.encode("utf-8")).hexdigest()[:8], 16)
        assignments = _allocate_groups(groups, stratum_seed, ratios)
        for group_id, group_rows in groups.items():
            for row in group_rows:
                row["split"] = assignments[group_id]
    return rows


def assert_no_group_leakage(rows: Sequence[dict[str, Any]]) -> None:
    seen: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        group_id = str(row.get("source_question_id") or row.get("generation_family") or "")
        if group_id:
            seen[group_id].add(str(row["split"]))
    leaked = {group: splits for group, splits in seen.items() if len(splits) > 1}
    if leaked:
        sample = next(iter(leaked.items()))
        raise ValueError(f"Grouped split leakage detected; example={sample}")


def validate_dataset(rows: Sequence[dict[str, Any]], valid_source_ids: set[str]) -> dict[str, Any]:
    if not rows:
        raise ValueError("Dataset is empty")
    normalized_labels: dict[str, set[int]] = defaultdict(set)
    for index, row in enumerate(rows, start=2):
        missing = [column for column in REQUIRED_COLUMNS if column not in row]
        if missing:
            raise ValueError(f"Row {index} is missing columns: {missing}")
        text = str(row["text"])
        if not text.strip():
            raise ValueError(f"Row {index} has empty text")
        label = int(row["label"])
        if label not in LABEL_MAP:
            raise ValueError(f"Row {index} has invalid label {label}")
        if label == LABEL_BANKING and str(row["source_question_id"]) not in valid_source_ids:
            raise ValueError(f"Label-0 row {index} lacks a real FAQ source")
        normalized_labels[normalize_persian(text, punctuation=True)].add(label)
    conflicts = [text for text, labels in normalized_labels.items() if len(labels) > 1]
    if conflicts:
        raise ValueError(f"Conflicting labels found for {len(conflicts)} normalized texts")
    assert_no_group_leakage(rows)
    counts = Counter(int(row["label"]) for row in rows)
    ratio = counts[LABEL_BANKING] / len(rows)
    if not 0.45 <= ratio <= 0.55:
        raise ValueError(f"Class balance outside 45%-55%: banking ratio={ratio:.4f}")
    return {"rows": len(rows), "labels": dict(counts), "banking_ratio": ratio}


def classification_metrics(labels: Sequence[int], predictions: Sequence[int]) -> dict[str, Any]:
    labels_array = np.asarray(labels, dtype=np.int64)
    predictions_array = np.asarray(predictions, dtype=np.int64)
    if labels_array.shape != predictions_array.shape or labels_array.size == 0:
        raise ValueError("Labels and predictions must be non-empty and equally shaped")
    matrix = np.zeros((2, 2), dtype=np.int64)
    for truth, predicted in zip(labels_array, predictions_array, strict=True):
        matrix[int(truth), int(predicted)] += 1
    per_class: dict[str, dict[str, float | int]] = {}
    for class_id, name in ((0, "banking"), (1, "chitchat_nonbanking")):
        tp = int(matrix[class_id, class_id])
        fp = int(matrix[1 - class_id, class_id])
        fn = int(matrix[class_id, 1 - class_id])
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[name] = {"precision": precision, "recall": recall, "f1": f1, "support": int((labels_array == class_id).sum())}
    return {
        "count": int(labels_array.size),
        "accuracy": float((labels_array == predictions_array).mean()),
        "macro_precision": float(np.mean([item["precision"] for item in per_class.values()])),
        "macro_recall": float(np.mean([item["recall"] for item in per_class.values()])),
        "macro_f1": float(np.mean([item["f1"] for item in per_class.values()])),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
        "banking_misrouted_to_chitchat": int(matrix[0, 1]),
        "banking_misrouted_to_chitchat_rate": float(matrix[0, 1] / matrix[0].sum()) if matrix[0].sum() else 0.0,
        "nonbanking_misrouted_to_banking": int(matrix[1, 0]),
        "nonbanking_misrouted_to_banking_rate": float(matrix[1, 0] / matrix[1].sum()) if matrix[1].sum() else 0.0,
    }


def subgroup_metrics(rows: Sequence[dict[str, Any]], predictions: Sequence[int]) -> dict[str, Any]:
    if len(rows) != len(predictions):
        raise ValueError("Rows and predictions differ in length")
    selectors = {
        "easy": lambda row: row["difficulty"] == "easy",
        "medium": lambda row: row["difficulty"] == "medium",
        "hard_positive": lambda row: row["example_type"] == "hard_positive",
        "hard_negative": lambda row: row["example_type"] == "hard_negative",
        "typo_variant": lambda row: row["example_type"] == "typo_variant",
        "short_query": lambda row: row["example_type"] == "short_variant",
        "conversational_banking": lambda row: int(row["label"]) == 0 and row["example_type"] in {"conversational_variant", "hard_negative"},
        "lexical_collision": lambda row: row["generation_family"].startswith("lexical_collision"),
    }
    result: dict[str, Any] = {}
    for name, selector in selectors.items():
        indices = [index for index, row in enumerate(rows) if selector(row)]
        if indices:
            result[name] = classification_metrics(
                [int(rows[index]["label"]) for index in indices],
                [int(predictions[index]) for index in indices],
            )
    return result


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def faq_as_dict(faq: FAQ) -> dict[str, str]:
    return asdict(faq)
