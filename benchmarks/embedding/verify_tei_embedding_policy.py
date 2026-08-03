#!/usr/bin/env python3
"""Non-writing smoke check for the production TEI embedding policies."""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from utils.tei_embedding_client import (
    EMBEDDING_DIMENSION,
    TeiEmbeddingClient,
    build_document_payload,
    build_query_payload,
)


AUDIT_QUERY = "چگونه می‌توانم رمز کارت خود را تغییر دهم؟"
AUDIT_DOCUMENTS = (
    "برای تغییر رمز کارت از بخش کارت‌ها وارد تنظیمات کارت شوید.",
    "در صورت فراموشی رمز، بازیابی رمز از برنامه امکان‌پذیر است.",
)


def norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


async def verify(tei_url: str) -> None:
    query_payload = build_query_payload(AUDIT_QUERY)
    document_payload = build_document_payload(AUDIT_DOCUMENTS)
    assert query_payload["prompt_name"] == "query"
    assert query_payload["normalize"] is True
    assert not query_payload["inputs"].startswith("Query: ")
    assert "prompt_name" not in document_payload
    assert document_payload["normalize"] is True

    async with httpx.AsyncClient(timeout=30.0) as http:
        client = TeiEmbeddingClient(tei_url, http)
        # Keep requests staged; this also avoids concurrent inference pressure.
        query_vector = await client.embed_query(AUDIT_QUERY)
        document_vectors = await client.embed_documents(AUDIT_DOCUMENTS)

    query_norm = norm(query_vector)
    document_norms = [norm(vector) for vector in document_vectors]
    assert len(query_vector) == EMBEDDING_DIMENSION
    assert all(len(vector) == EMBEDDING_DIMENSION for vector in document_vectors)
    assert math.isclose(query_norm, 1.0, rel_tol=1e-3, abs_tol=1e-3)
    assert all(
        math.isclose(value, 1.0, rel_tol=1e-3, abs_tol=1e-3)
        for value in document_norms
    )

    print("query_prompt_name=query")
    print("query_normalize=true")
    print("document_prompt_name=absent")
    print("document_normalize=true")
    print(f"query_dimension={len(query_vector)} query_norm={query_norm:.6f}")
    print(
        "document_dimensions="
        f"{[len(vector) for vector in document_vectors]} "
        f"document_norms={[round(value, 6) for value in document_norms]}"
    )
    print("qdrant_writes=0")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tei-url",
        default=os.getenv("TEI_EMBED_URL"),
        help="TEI base URL; defaults to TEI_EMBED_URL",
    )
    args = parser.parse_args()
    if not args.tei_url:
        parser.error("--tei-url or TEI_EMBED_URL is required")
    asyncio.run(verify(args.tei_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
