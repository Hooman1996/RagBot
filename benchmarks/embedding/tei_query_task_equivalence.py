#!/usr/bin/env python3
"""Compare local SentenceTransformer and TEI query-task semantics.

The workflow is deliberately split into independent stages:

1. ``local`` loads SentenceTransformer and writes local vectors.
2. ``tei`` calls the already-running TEI service and writes TEI vectors.
3. ``analyze`` queries Qdrant and writes comparison/evaluation reports.

Run the local stage on CPU while TEI is resident, or stop TEI before selecting
a CUDA device. The script never starts, stops, or reconfigures a service.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "1.0"
QUERY_PREFIX = "Query: "
DOCUMENT_PREFIX = "Document: "


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def fixture_queries(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("fixture must contain a non-empty 'queries' list")
    for item in queries:
        if not isinstance(item.get("id"), str) or not isinstance(item.get("query"), str):
            raise ValueError("every fixture query needs string 'id' and 'query' fields")
        relevant = item.get("relevant_ids")
        if not isinstance(relevant, list) or not all(
            isinstance(point_id, (int, str)) for point_id in relevant
        ):
            raise ValueError("every fixture query needs a 'relevant_ids' list")
    return queries


def norm(vector: Iterable[float]) -> float:
    return math.sqrt(sum(float(value) ** 2 for value in vector))


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError(f"dimension mismatch: {len(left)} != {len(right)}")
    denominator = norm(left) * norm(right)
    if denominator == 0:
        raise ValueError("cosine similarity is undefined for a zero vector")
    return sum(float(a) * float(b) for a, b in zip(left, right)) / denominator


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"{method} {url} returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def validate_vectors(vectors: Any, expected_count: int, label: str) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != expected_count:
        raise ValueError(f"{label}: expected {expected_count} vectors")
    dimensions = set()
    validated: list[list[float]] = []
    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            raise ValueError(f"{label}: invalid vector response")
        converted = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in converted):
            raise ValueError(f"{label}: non-finite vector value")
        dimensions.add(len(converted))
        validated.append(converted)
    if len(dimensions) != 1:
        raise ValueError(f"{label}: inconsistent output dimensions")
    return validated


def index_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {record["id"]: record for record in records}


def local_stage(args: argparse.Namespace) -> None:
    if args.device.startswith("cuda") and not args.tei_confirmed_stopped:
        raise SystemExit(
            "Refusing local CUDA inference without --tei-confirmed-stopped. "
            "Use --device cpu while TEI is running."
        )

    import sentence_transformers
    import torch
    import transformers
    from sentence_transformers import SentenceTransformer

    queries = fixture_queries(args.fixture)
    texts = [item["query"] for item in queries]
    started = time.perf_counter_ns()
    model = SentenceTransformer(
        str(args.model),
        device=args.device,
        trust_remote_code=True,
        local_files_only=True,
    )

    encode_kwargs = {
        "batch_size": args.batch_size,
        "show_progress_bar": False,
        "convert_to_numpy": True,
        "normalize_embeddings": True,
    }
    task_vectors = model.encode(texts, task="retrieval.query", **encode_kwargs)
    raw_vectors = model.encode(texts, **encode_kwargs)
    prompted_vectors = model.encode(texts, prompt_name="query", **encode_kwargs)

    records = []
    for index, query in enumerate(queries):
        records.append(
            {
                "id": query["id"],
                "vector": task_vectors[index].tolist(),
                "controls": {
                    "raw": raw_vectors[index].tolist(),
                    "prompt_name_query": prompted_vectors[index].tolist(),
                },
            }
        )

    provenance = []
    if args.provenance_ids:
        try:
            from parsivar import Normalizer

            normalizer = Normalizer()
        except ImportError:
            normalizer = None

        point_ids = [int(value) for value in args.provenance_ids.split(",") if value]
        documents = []
        valid_ids = []
        for point_id in point_ids:
            chunk = args.chunk_dir / f"General_FAQ_{point_id - 1}.txt"
            if not chunk.exists():
                continue
            text = chunk.read_text(encoding="utf-8")
            documents.append(normalizer.normalize(text) if normalizer else text)
            valid_ids.append(point_id)
        if documents:
            raw_documents = model.encode(documents, **encode_kwargs)
            task_documents = model.encode(
                documents, task="retrieval.passage", **encode_kwargs
            )
            prompted_documents = model.encode(
                documents, prompt_name="document", **encode_kwargs
            )
            for index, point_id in enumerate(valid_ids):
                provenance.append(
                    {
                        "point_id": point_id,
                        "raw": raw_documents[index].tolist(),
                        "task_retrieval_passage": task_documents[index].tolist(),
                        "prompt_name_document": prompted_documents[index].tolist(),
                    }
                )

    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    write_json(
        args.output,
        {
            "schema_version": SCHEMA_VERSION,
            "stage": "local",
            "model": str(args.model),
            "device": args.device,
            "versions": {
                "python": platform.python_version(),
                "torch": torch.__version__,
                "transformers": transformers.__version__,
                "sentence_transformers": sentence_transformers.__version__,
            },
            "method_a": {
                "call": "encode(task='retrieval.query', normalize_embeddings=True)",
                "records": records,
            },
            "document_provenance_controls": provenance,
            "elapsed_ms": elapsed_ms,
        },
    )


def tei_embed(
    base_url: str,
    inputs: list[str],
    *,
    prompt_name: str | None = None,
    normalize: bool | None = True,
    timeout: float,
) -> list[list[float]]:
    payload: dict[str, Any] = {"inputs": inputs}
    if prompt_name is not None:
        payload["prompt_name"] = prompt_name
    if normalize is not None:
        payload["normalize"] = normalize
    response = http_json("POST", f"{base_url.rstrip('/')}/embed", payload, timeout)
    return validate_vectors(response, len(inputs), "TEI /embed")


def tei_stage(args: argparse.Namespace) -> None:
    queries = fixture_queries(args.fixture)
    texts = [item["query"] for item in queries]
    started = time.perf_counter_ns()
    info = http_json("GET", f"{args.tei_url.rstrip('/')}/info", timeout=args.timeout)

    raw = tei_embed(args.tei_url, texts, normalize=True, timeout=args.timeout)
    prompted = tei_embed(
        args.tei_url, texts, prompt_name="query", normalize=True, timeout=args.timeout
    )
    manual = tei_embed(
        args.tei_url,
        [QUERY_PREFIX + text for text in texts],
        normalize=True,
        timeout=args.timeout,
    )
    normalization_probe = {
        "normalize_true": tei_embed(
            args.tei_url, [texts[0]], normalize=True, timeout=args.timeout
        )[0],
        "normalize_false": tei_embed(
            args.tei_url, [texts[0]], normalize=False, timeout=args.timeout
        )[0],
        "property_omitted": tei_embed(
            args.tei_url, [texts[0]], normalize=None, timeout=args.timeout
        )[0],
    }

    records = []
    for index, query in enumerate(queries):
        records.append(
            {
                "id": query["id"],
                "b_raw": raw[index],
                "c_prompt_name_query": prompted[index],
                "d_manual_query_prefix": manual[index],
            }
        )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    write_json(
        args.output,
        {
            "schema_version": SCHEMA_VERSION,
            "stage": "tei",
            "tei_url": args.tei_url,
            "info": info,
            "records": records,
            "normalization_probe": normalization_probe,
            "elapsed_ms": elapsed_ms,
        },
    )


def qdrant_query(
    base_url: str,
    collection: str,
    vector: list[float],
    limit: int,
    timeout: float,
) -> list[dict[str, Any]]:
    payload = {
        "query": vector,
        "limit": limit,
        "with_payload": True,
        "with_vector": False,
    }
    response = http_json(
        "POST",
        f"{base_url.rstrip('/')}/collections/{collection}/points/query",
        payload,
        timeout,
    )
    points = response.get("result", {}).get("points")
    if not isinstance(points, list):
        raise ValueError("Qdrant query returned an invalid point list")
    return [
        {
            "id": point["id"],
            "score": float(point["score"]),
            "chunk_index": point.get("payload", {}).get("chunk_index"),
            "document": point.get("payload", {}).get("document"),
        }
        for point in points
    ]


def qdrant_vectors(
    base_url: str,
    collection: str,
    point_ids: list[int],
    timeout: float,
) -> dict[int, list[float]]:
    if not point_ids:
        return {}
    response = http_json(
        "POST",
        f"{base_url.rstrip('/')}/collections/{collection}/points",
        {"ids": point_ids, "with_payload": False, "with_vector": True},
        timeout,
    )
    points = response.get("result")
    if not isinstance(points, list):
        raise ValueError("Qdrant point retrieval returned an invalid response")
    return {int(point["id"]): [float(v) for v in point["vector"]] for point in points}


def ranked_ids(results: list[dict[str, Any]]) -> list[Any]:
    return [point["id"] for point in results]


def overlap_at_k(left: list[Any], right: list[Any], k: int) -> float:
    return len(set(left[:k]) & set(right[:k])) / k


def rank_and_score_changes(
    baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    baseline_rank = {point["id"]: index + 1 for index, point in enumerate(baseline)}
    candidate_rank = {point["id"]: index + 1 for index, point in enumerate(candidate)}
    baseline_score = {point["id"]: point["score"] for point in baseline}
    candidate_score = {point["id"]: point["score"] for point in candidate}
    changes = []
    for point_id in sorted(set(baseline_rank) | set(candidate_rank), key=str):
        old_rank = baseline_rank.get(point_id)
        new_rank = candidate_rank.get(point_id)
        changes.append(
            {
                "id": point_id,
                "a_rank": old_rank,
                "candidate_rank": new_rank,
                "rank_delta": (
                    new_rank - old_rank
                    if old_rank is not None and new_rank is not None
                    else None
                ),
                "a_score": baseline_score.get(point_id),
                "candidate_score": candidate_score.get(point_id),
                "score_delta": (
                    candidate_score[point_id] - baseline_score[point_id]
                    if point_id in baseline_score and point_id in candidate_score
                    else None
                ),
            }
        )
    return changes


def retrieval_metrics(
    queries: list[dict[str, Any]], results_by_query: dict[str, list[dict[str, Any]]]
) -> dict[str, float | int]:
    top1_hits = 0
    top3_hits = 0
    recall3 = 0.0
    recall10 = 0.0
    reciprocal_rank = 0.0
    for query in queries:
        relevant = {str(value) for value in query["relevant_ids"]}
        retrieved = [
            str(point["id"]) for point in results_by_query[query["id"]][:10]
        ]
        top1_hits += int(bool(relevant & set(retrieved[:1])))
        top3_hits += int(bool(relevant & set(retrieved[:3])))
        recall3 += len(relevant & set(retrieved[:3])) / len(relevant)
        recall10 += len(relevant & set(retrieved[:10])) / len(relevant)
        first_rank = next(
            (index + 1 for index, point_id in enumerate(retrieved) if point_id in relevant),
            None,
        )
        reciprocal_rank += 1.0 / first_rank if first_rank else 0.0
    count = len(queries)
    return {
        "queries": count,
        "top_1_accuracy": top1_hits / count,
        "top_3_accuracy": top3_hits / count,
        "recall_at_3": recall3 / count,
        "recall_at_10": recall10 / count,
        "mrr_at_10": reciprocal_rank / count,
    }


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# TEI query-task equivalence measured results",
        "",
        "| Query | dim A/B/C/D | norm A/B/C/D | cos(A,B) | cos(A,C) | cos(A,D) | overlap A/B | overlap A/C | overlap A/D |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for query in payload["queries"]:
        dims = "/".join(str(query["dimensions"][key]) for key in ("a", "b", "c", "d"))
        norms = "/".join(f"{query['norms'][key]:.6f}" for key in ("a", "b", "c", "d"))
        lines.append(
            f"| {query['id']} | {dims} | {norms} | "
            f"{query['cosine']['a_b']:.8f} | {query['cosine']['a_c']:.8f} | "
            f"{query['cosine']['a_d']:.8f} | {query['overlap_at_10']['a_b']:.2f} | "
            f"{query['overlap_at_10']['a_c']:.2f} | {query['overlap_at_10']['a_d']:.2f} |"
        )
        for method in ("a", "b", "c", "d"):
            scored_ids = ", ".join(
                f"{point['id']}@{point['score']:.6f}"
                for point in query["top_10_results"][method]
            )
            lines.append(
                f"| ↳ {method.upper()} ID@score | `{scored_ids}` |  |  |  |  |  |  |  |"
            )
        lines.extend(
            [
                "",
                f"Rank and score changes for `{query['id']}` relative to A:",
                "",
                "| Candidate | Moved shared IDs | Entered / exited | Mean absolute score Δ | Max absolute score Δ |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for method in ("b", "c", "d"):
            changes = query["changes_from_a"][method]
            shared = [
                item
                for item in changes
                if item["a_rank"] is not None and item["candidate_rank"] is not None
            ]
            moved = sum(item["rank_delta"] != 0 for item in shared)
            entered = sum(item["a_rank"] is None for item in changes)
            exited = sum(item["candidate_rank"] is None for item in changes)
            score_deltas = [abs(item["score_delta"]) for item in shared]
            mean_delta = sum(score_deltas) / len(score_deltas) if score_deltas else 0.0
            max_delta = max(score_deltas, default=0.0)
            lines.append(
                f"| {method.upper()} | {moved}/{len(shared)} | {entered} / {exited} | "
                f"{mean_delta:.6f} | {max_delta:.6f} |"
            )
        lines.append("")
    lines.extend(
        [
            "",
            "## Retrieval evaluation",
            "",
            "| Method | Top-1 accuracy | Top-3 accuracy | Recall@3 | Recall@10 | MRR@10 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for method, metrics in payload["retrieval_evaluation"].items():
        lines.append(
            f"| {method.upper()} | {metrics['top_1_accuracy']:.4f} | "
            f"{metrics['top_3_accuracy']:.4f} | {metrics['recall_at_3']:.4f} | "
            f"{metrics['recall_at_10']:.4f} | {metrics['mrr_at_10']:.4f} |"
        )
    return "\n".join(lines) + "\n"


def analyze_stage(args: argparse.Namespace) -> None:
    queries = fixture_queries(args.fixture)
    local = read_json(args.local_results)
    tei = read_json(args.tei_results)
    local_records = index_by_id(local["method_a"]["records"])
    tei_records = index_by_id(tei["records"])

    measured_queries = []
    method_results: dict[str, dict[str, list[dict[str, Any]]]] = {
        method: {} for method in ("a", "b", "c", "d")
    }
    for query in queries:
        query_id = query["id"]
        vectors = {
            "a": local_records[query_id]["vector"],
            "b": tei_records[query_id]["b_raw"],
            "c": tei_records[query_id]["c_prompt_name_query"],
            "d": tei_records[query_id]["d_manual_query_prefix"],
        }
        results = {
            method: qdrant_query(
                args.qdrant_url,
                args.collection,
                vector,
                args.limit,
                args.timeout,
            )
            for method, vector in vectors.items()
        }
        for method in results:
            method_results[method][query_id] = results[method]
        measured_queries.append(
            {
                "id": query_id,
                "query": query["query"],
                "relevant_ids": query["relevant_ids"],
                "dimensions": {key: len(value) for key, value in vectors.items()},
                "norms": {key: norm(value) for key, value in vectors.items()},
                "cosine": {
                    "a_b": cosine(vectors["a"], vectors["b"]),
                    "a_c": cosine(vectors["a"], vectors["c"]),
                    "a_d": cosine(vectors["a"], vectors["d"]),
                    "c_d": cosine(vectors["c"], vectors["d"]),
                },
                "top_10_ids": {
                    key: ranked_ids(value) for key, value in results.items()
                },
                "top_10_results": results,
                "overlap_at_10": {
                    "a_b": overlap_at_k(
                        ranked_ids(results["a"]), ranked_ids(results["b"]), 10
                    ),
                    "a_c": overlap_at_k(
                        ranked_ids(results["a"]), ranked_ids(results["c"]), 10
                    ),
                    "a_d": overlap_at_k(
                        ranked_ids(results["a"]), ranked_ids(results["d"]), 10
                    ),
                },
                "changes_from_a": {
                    key: rank_and_score_changes(results["a"], results[key])
                    for key in ("b", "c", "d")
                },
            }
        )

    provenance_controls = local.get("document_provenance_controls", [])
    stored_vectors = qdrant_vectors(
        args.qdrant_url,
        args.collection,
        [item["point_id"] for item in provenance_controls],
        args.timeout,
    )
    provenance = []
    for item in provenance_controls:
        stored = stored_vectors.get(item["point_id"])
        if stored is None:
            continue
        provenance.append(
            {
                "point_id": item["point_id"],
                "dimension": len(stored),
                "norm": norm(stored),
                "cosine_to_local_raw": cosine(stored, item["raw"]),
                "cosine_to_task_retrieval_passage": cosine(
                    stored, item["task_retrieval_passage"]
                ),
                "cosine_to_prompt_name_document": cosine(
                    stored, item["prompt_name_document"]
                ),
                "local_raw_vs_task_retrieval_passage": cosine(
                    item["raw"], item["task_retrieval_passage"]
                ),
            }
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "fixture": str(args.fixture),
        "collection": args.collection,
        "queries": measured_queries,
        "normalization_probe_norms": {
            key: norm(value) for key, value in tei["normalization_probe"].items()
        },
        "retrieval_evaluation": {
            method: retrieval_metrics(queries, method_results[method])
            for method in ("a", "b", "c", "d")
        },
        "qdrant_document_vector_provenance": provenance,
        "local_semantic_controls": {
            query["id"]: {
                "task_vs_raw": cosine(
                    local_records[query["id"]]["vector"],
                    local_records[query["id"]]["controls"]["raw"],
                ),
                "task_vs_prompt_name_query": cosine(
                    local_records[query["id"]]["vector"],
                    local_records[query["id"]]["controls"]["prompt_name_query"],
                ),
            }
            for query in queries
        },
    }
    write_json(args.output, payload)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(markdown_report(payload), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="stage", required=True)

    local = subparsers.add_parser("local", help="generate method A locally")
    local.add_argument("--fixture", type=Path, required=True)
    local.add_argument("--model", type=Path, required=True)
    local.add_argument("--output", type=Path, required=True)
    local.add_argument("--device", default="cpu")
    local.add_argument("--batch-size", type=int, default=2)
    local.add_argument("--tei-confirmed-stopped", action="store_true")
    local.add_argument(
        "--chunk-dir",
        type=Path,
        default=Path("data_insertion_chunks/CHUNKS/General_FAQ"),
    )
    local.add_argument(
        "--provenance-ids",
        default="1,74,100,148,203,444,596,657,682,765",
    )
    local.set_defaults(function=local_stage)

    tei = subparsers.add_parser("tei", help="generate methods B, C, and D via TEI")
    tei.add_argument("--fixture", type=Path, required=True)
    tei.add_argument("--tei-url", required=True)
    tei.add_argument("--output", type=Path, required=True)
    tei.add_argument("--timeout", type=float, default=60.0)
    tei.set_defaults(function=tei_stage)

    analyze = subparsers.add_parser("analyze", help="query Qdrant and report metrics")
    analyze.add_argument("--fixture", type=Path, required=True)
    analyze.add_argument("--local-results", type=Path, required=True)
    analyze.add_argument("--tei-results", type=Path, required=True)
    analyze.add_argument("--qdrant-url", required=True)
    analyze.add_argument("--collection", required=True)
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--markdown-output", type=Path, required=True)
    analyze.add_argument("--limit", type=int, default=10)
    analyze.add_argument("--timeout", type=float, default=30.0)
    analyze.set_defaults(function=analyze_stage)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.function(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
