# app/models/embedding.py

"""
Embedding Model - Minimal Safe Version
=======================================
Vector embeddings for semantic search
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Index, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY
from datetime import datetime
import uuid

from ..core.database import Base


class Embedding(Base):
    """Embedding model - vector representations of text chunks"""

    __tablename__ = "embeddings"

    # ═══════════════════════════════════════════════════════════
    # PRIMARY KEY
    # ═══════════════════════════════════════════════════════════

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))

    # ═══════════════════════════════════════════════════════════
    # FOREIGN KEYS
    # ═══════════════════════════════════════════════════════════

    chunk_id = Column(
        Integer,
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True  # One embedding per chunk
    )

    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    # Denormalized for faster queries

    # ═══════════════════════════════════════════════════════════
    # EMBEDDING DATA
    # ═══════════════════════════════════════════════════════════

    # Option 1: Store embedding as PostgreSQL array (if using pgvector)
    # vector = Column(ARRAY(Float), nullable=False)

    # Option 2: Store embedding as JSON (more compatible)
    vector = Column(JSON, nullable=False)
    # Example: [0.123, -0.456, 0.789, ...]

    vector_dimension = Column(Integer, nullable=False)
    # Dimension of the vector: 384, 768, 1536, etc.

    # ═══════════════════════════════════════════════════════════
    # MODEL INFO
    # ═══════════════════════════════════════════════════════════

    model_name = Column(String(100), nullable=False)
    # Model used: text-embedding-ada-002, all-MiniLM-L6-v2, etc.

    model_version = Column(String(50))
    # Version of the model

    # ═══════════════════════════════════════════════════════════
    # VECTOR DATABASE INFO
    # ═══════════════════════════════════════════════════════════

    vector_db_id = Column(String(100), index=True)
    # ID in vector database (e.g., Qdrant point ID, Pinecone ID)

    vector_db_collection = Column(String(100))
    # Collection/index name in vector database

    # ═══════════════════════════════════════════════════════════
    # SOURCE TEXT (for debugging/verification)
    # ═══════════════════════════════════════════════════════════

    source_text = Column(Text)
    # Original text that was embedded (optional, for verification)

    source_text_hash = Column(String(64), index=True)
    # Hash of source text for deduplication

    # ═══════════════════════════════════════════════════════════
    # METADATA
    # ═══════════════════════════════════════════════════════════

    meta_data = Column(JSON, default=dict)
    # Additional metadata: language, processing_time, etc.

    # ═══════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════

    status = Column(String(50), default="active")
    # Status: active, outdated, failed

    # ═══════════════════════════════════════════════════════════
    # TIMESTAMPS
    # ═══════════════════════════════════════════════════════════

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ═══════════════════════════════════════════════════════════
    # RELATIONSHIPS - MINIMAL
    # ═══════════════════════════════════════════════════════════

    chunk = relationship(
        "Chunk",
        backref="embedding",  # Use backref instead of back_populates
        uselist=False  # One-to-one relationship
    )

    document = relationship(
        "Document",
        backref="embeddings"  # Use backref
    )

    # ═══════════════════════════════════════════════════════════
    # INDEXES
    # ═══════════════════════════════════════════════════════════

    __table_args__ = (
        Index('idx_document_model', 'document_id', 'model_name'),
        Index('idx_vector_db', 'vector_db_id', 'vector_db_collection'),
        Index('idx_status_model', 'status', 'model_name'),
    )

    def __repr__(self):
        return f"<Embedding(id={self.id}, chunk_id={self.chunk_id}, model='{self.model_name}', dim={self.vector_dimension})>"

    @property
    def vector_preview(self):
        """Get preview of vector (first 5 dimensions)"""
        if isinstance(self.vector, list) and len(self.vector) > 5:
            preview = [round(v, 4) for v in self.vector[:5]]
            return f"{preview}..."
        return self.vector