import os
from dotenv import load_dotenv
load_dotenv()


import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
import uuid

import torch.cuda
import torch
# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# ═══════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from ...config import Config
import psycopg2
import psycopg2.extras

class EmbeddingService:
    """Service for generating embeddings"""

    def __init__(self, model_name: str = os.getenv("EMBEDDING_MODEL_NAME")):
        self.model_name = model_name
        self.model = None
        self._load_model()

    def _load_model(self):
        """Load embedding model"""
        print()
        print("=" * 80)
        print("LOADING EMBEDDING MODEL")
        print("=" * 80)
        print()

        print(f"→ Loading model: {self.model_name}")

        try:
            from sentence_transformers import SentenceTransformer
            device = 'cuda:1' if torch.cuda.is_available() else 'cpu'
            print(f"Loading embedding model on {device}...")
            self.model = SentenceTransformer(self.model, device=device, trust_remote_code=True, local_files_only=True)

            print(f"  ✓ Model loaded")
            print()

        except Exception as e:
            print(f"  ❌ Failed to load model: {e}")
            print()
            self.model = None

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for texts

        Args:
            texts: List of texts

        Returns:
            List of embedding vectors
        """
        print()
        print("=" * 80)
        print("GENERATING EMBEDDINGS")
        print("=" * 80)
        print()

        print(f"→ Generating embeddings for {len(texts)} texts...")

        if not self.model:
            print(f"  ❌ Model not loaded")
            print()
            return []

        try:
            embeddings = self.model.encode(texts, show_progress_bar=True)

            print(f"  ✓ Generated {len(embeddings)} embeddings")
            print(f"    Dimension: {len(embeddings[0])}")
            print()

            return embeddings.tolist()

        except Exception as e:
            print(f"  ❌ Embedding generation failed: {e}")
            print()
            return []

    def save_embeddings_to_qdrant(
            self,
            qdrant_client: QdrantClient,
            embeddings: List[List[float]],
            chunk_ids: List[int],
            document_id: int
    ) -> bool:
        """
        Save embeddings to Qdrant

        Args:
            qdrant_client: Qdrant client
            embeddings: List of embedding vectors
            chunk_ids: List of chunk IDs
            document_id: Document ID

        Returns:
            True if successful
        """
        print()
        print("=" * 80)
        print("SAVING EMBEDDINGS TO QDRANT")
        print("=" * 80)
        print()

        print(f"→ Saving {len(embeddings)} embeddings to Qdrant...")

        try:
            points = []

            for i, (embedding, chunk_id) in enumerate(zip(embeddings, chunk_ids)):
                point = PointStruct(
                    id=chunk_id,  # Use chunk_id as point ID
                    vector=embedding,
                    payload={
                        'chunk_id': chunk_id,
                        'document_id': document_id,
                        'chunk_index': i
                    }
                )
                points.append(point)

            qdrant_client.upsert(
                collection_name=Config.QDRANT_COLLECTION,
                points=points
            )

            print(f"  ✓ Saved {len(points)} embeddings to Qdrant")
            print()

            return True

        except Exception as e:
            print(f"  ❌ Failed to save embeddings: {e}")
            print()
            return False

    def save_embeddings_to_db(
            self,
            db_conn,
            embeddings: List[List[float]],
            chunk_ids: List[int],
            document_id: int
    ) -> bool:
        """
        Save embedding metadata to PostgreSQL

        Args:
            db_conn: Database connection
            embeddings: List of embedding vectors
            chunk_ids: List of chunk IDs
            document_id: Document ID

        Returns:
            True if successful
        """
        print()
        print("=" * 80)
        print("SAVING EMBEDDING METADATA TO DATABASE")
        print("=" * 80)
        print()

        print(f"→ Saving {len(embeddings)} embedding records...")

        try:
            cursor = db_conn.cursor()

            for embedding, chunk_id in zip(embeddings, chunk_ids):
                cursor.execute("""
                               INSERT INTO embeddings (uuid, chunk_id, document_id, vector,
                                                       vector_dimension, model_name, model_version,
                                                       vector_db_id, vector_db_collection,
                                                       status, created_at, updated_at)
                               VALUES (gen_random_uuid()::text, %s, %s, %s,
                                       %s, %s, %s,
                                       %s, %s,
                                       %s, %s, %s)
                               """, (
                                   chunk_id,
                                   document_id,
                                   json.dumps(embedding),
                                   len(embedding),
                                   self.model_name,
                                   '1.0',
                                   str(chunk_id),  # Using chunk_id as Qdrant point ID
                                   Config.QDRANT_COLLECTION,
                                   'active',
                                   datetime.utcnow(),
                                   datetime.utcnow()
                               ))

            db_conn.commit()

            print(f"  ✓ Saved {len(embeddings)} embedding records")
            print()

            cursor.close()

            return True

        except Exception as e:
            print(f"  ❌ Failed to save embeddings: {e}")
            print()
            return False

