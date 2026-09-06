"""Cache embeddings acquired only through the live shared query client."""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Sequence
from urllib.parse import urlsplit, urlunsplit

import httpx
import numpy as np

from utils.persian_normalization import normalize_persian_text
from utils.tei_embedding_client import (
    EMBEDDING_DIMENSION,
    QUERY_PROMPT_NAME,
    TeiEmbeddingClient,
)


EMBEDDING_POLICY = "retrieval_query_v1"


def _fingerprint(text: str) -> str:
    normalized = normalize_persian_text(text)
    return hashlib.sha256(
        f"{EMBEDDING_POLICY}\x1f{normalized}".encode("utf-8")
    ).hexdigest()


class EmbeddingCache:
    def __init__(self, path: Path, *, dataset_fingerprint: str) -> None:
        self.path = path
        self.dataset_fingerprint = dataset_fingerprint
        self._vectors: dict[str, np.ndarray] = {}
        if not path.exists():
            return
        payload = np.load(path, allow_pickle=False)
        metadata = {
            "policy": str(payload["policy"].item()),
            "role": str(payload["role"].item()),
            "prompt_name": str(payload["prompt_name"].item()),
            "normalizer": str(payload["normalizer"].item()),
            "normalize": bool(payload["normalize"].item()),
            "dimension": int(payload["dimension"].item()),
            "dataset_fingerprint": (
                str(payload["dataset_fingerprint"].item())
                if "dataset_fingerprint" in payload.files
                else None
            ),
        }
        expected = {
            "policy": EMBEDDING_POLICY,
            "role": "retrieval_query",
            "prompt_name": QUERY_PROMPT_NAME,
            "normalizer": "normalize_persian_text",
            "normalize": True,
            "dimension": EMBEDDING_DIMENSION,
            "dataset_fingerprint": dataset_fingerprint,
        }
        if metadata != expected:
            raise ValueError(f"Embedding cache policy mismatch: {metadata!r}")
        vectors = payload["vectors"]
        keys = payload["keys"]
        if vectors.shape != (len(keys), EMBEDDING_DIMENSION):
            raise ValueError(f"Invalid embedding cache shape: {vectors.shape}")
        self._vectors = {
            str(key): np.asarray(vector, dtype=np.float32)
            for key, vector in zip(keys, vectors, strict=True)
        }

    def get(self, text: str) -> np.ndarray | None:
        return self._vectors.get(_fingerprint(text))

    def put(self, text: str, vector: Sequence[float]) -> None:
        array = np.asarray(vector, dtype=np.float32)
        if array.shape != (EMBEDDING_DIMENSION,) or not np.isfinite(array).all():
            raise ValueError(f"Invalid query embedding shape/content: {array.shape}")
        self._vectors[_fingerprint(text)] = array

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        keys = np.asarray(sorted(self._vectors), dtype="U64")
        vectors = (
            np.stack([self._vectors[key] for key in keys])
            if len(keys)
            else np.empty((0, EMBEDDING_DIMENSION), dtype=np.float32)
        )
        temporary = self.path.with_suffix(self.path.suffix + ".tmp.npz")
        np.savez(
            temporary,
            policy=np.asarray(EMBEDDING_POLICY),
            role=np.asarray("retrieval_query"),
            prompt_name=np.asarray(QUERY_PROMPT_NAME),
            normalizer=np.asarray("normalize_persian_text"),
            normalize=np.asarray(True),
            dimension=np.asarray(EMBEDDING_DIMENSION),
            dataset_fingerprint=np.asarray(self.dataset_fingerprint),
            keys=keys,
            vectors=vectors,
        )
        temporary.replace(self.path)


def resolve_tei_url(explicit_url: str | None) -> str:
    value = explicit_url or os.getenv("TEI_EMBED_URL")
    if not value or not value.strip():
        raise ValueError("TEI_EMBED_URL must be configured")
    return value.rstrip("/")


def tei_endpoint_identity(tei_url: str) -> str:
    """Return a credential-free endpoint identifier for artifact provenance."""
    parts = urlsplit(tei_url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("TEI_EMBED_URL must be an HTTP(S) URL")
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{parts.port}" if parts.port is not None else host
    base_path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, netloc, f"{base_path}/embed", "", ""))


async def _embed_missing(
    texts: list[str],
    *,
    cache: EmbeddingCache,
    tei_url: str,
    request_concurrency: int,
    timeout: float,
) -> None:
    limits = httpx.Limits(
        max_connections=request_concurrency,
        max_keepalive_connections=request_concurrency,
    )
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as http_client:
        shared_client = TeiEmbeddingClient(
            tei_url,
            http_client,
            expected_dimension=EMBEDDING_DIMENSION,
        )
        completed = 0
        for offset in range(0, len(texts), request_concurrency):
            batch = texts[offset : offset + request_concurrency]
            # Runtime normalizes before _encode_query, whose shared client/payload
            # builder normalizes again. Training deliberately follows that path.
            normalized = [normalize_persian_text(text) for text in batch]
            vectors = await asyncio.gather(
                *(shared_client.embed_query(text) for text in normalized)
            )
            for text, vector in zip(batch, vectors, strict=True):
                cache.put(text, vector)
            completed += len(batch)
            if completed % 2048 < request_concurrency or completed == len(texts):
                cache.save()
                print(f"retrieval-query embeddings cached: {completed}/{len(texts)}")


def embed_texts(
    texts: Sequence[str],
    *,
    cache_path: Path,
    dataset_fingerprint: str,
    tei_url: str | None = None,
    request_concurrency: int = 16,
    timeout: float = 60.0,
) -> np.ndarray:
    if request_concurrency < 1:
        raise ValueError("request_concurrency must be positive")
    if not dataset_fingerprint:
        raise ValueError("dataset_fingerprint must be present")
    cache = EmbeddingCache(
        cache_path, dataset_fingerprint=dataset_fingerprint
    )
    missing = list(dict.fromkeys(text for text in texts if cache.get(text) is None))
    if missing:
        asyncio.run(
            _embed_missing(
                missing,
                cache=cache,
                tei_url=resolve_tei_url(tei_url),
                request_concurrency=request_concurrency,
                timeout=timeout,
            )
        )
    vectors = [cache.get(text) for text in texts]
    if any(vector is None for vector in vectors):
        raise RuntimeError("Embedding cache is incomplete")
    return np.stack(vectors).astype(np.float32, copy=False)
