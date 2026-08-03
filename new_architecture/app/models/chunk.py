# app/models/chunk.py

"""
Chunk Model - Minimal Safe Version
===================================
Text chunks from documents for RAG
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..core.database import Base


class Chunk(Base):
    """Chunk model - text segments from documents with embeddings"""

    __tablename__ = "chunks"

    # ═══════════════════════════════════════════════════════════
    # PRIMARY KEY
    # ═══════════════════════════════════════════════════════════

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))

    # ═══════════════════════════════════════════════════════════
    # FOREIGN KEYS
    # ═══════════════════════════════════════════════════════════

    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # ═══════════════════════════════════════════════════════════
    # CHUNK DATA
    # ═══════════════════════════════════════════════════════════

    content = Column(Text, nullable=False)
    # The actual text content of the chunk

    chunk_index = Column(Integer, nullable=False)
    # Position of this chunk in the document (0-based)

    chunk_type = Column(String(50), default="text")
    # Type: text, heading, list, table, code, etc.

    # ═══════════════════════════════════════════════════════════
    # EMBEDDING DATA
    # ═══════════════════════════════════════════════════════════

    embedding_id = Column(String(100))
    # Reference to embedding in vector database (e.g., Qdrant point ID)

    embedding_model = Column(String(100))
    # Model used for embedding: text-embedding-ada-002, all-MiniLM-L6-v2, etc.

    # ═══════════════════════════════════════════════════════════
    # CHUNK METADATA
    # ═══════════════════════════════════════════════════════════

    token_count = Column(Integer)
    # Number of tokens in this chunk

    char_count = Column(Integer)
    # Number of characters in this chunk

    start_char = Column(Integer)
    # Start position in original document

    end_char = Column(Integer)
    # End position in original document

    page_number = Column(Integer)
    # Page number (for PDFs)

    # ═══════════════════════════════════════════════════════════
    # ADDITIONAL METADATA
    # ═══════════════════════════════════════════════════════════

    meta_data = Column(JSON, default=dict)
    # Additional metadata: language, section, heading, etc.

    # ═══════════════════════════════════════════════════════════
    # TIMESTAMPS
    # ═══════════════════════════════════════════════════════════

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ═══════════════════════════════════════════════════════════
    # RELATIONSHIPS - MINIMAL
    # ═══════════════════════════════════════════════════════════

    document = relationship(
        "Document",
        back_populates="chunks"
    )

    # ═══════════════════════════════════════════════════════════
    # INDEXES
    # ═══════════════════════════════════════════════════════════

    __table_args__ = (
        # Composite index for efficient querying
        Index('idx_document_chunk', 'document_id', 'chunk_index'),
        Index('idx_document_embedding', 'document_id', 'embedding_id'),
    )

    def __repr__(self):
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Chunk(id={self.id}, document_id={self.document_id}, index={self.chunk_index}, content='{preview}')>"

    @property
    def content_preview(self):
        """Get preview of content (first 100 chars)"""
        if len(self.content) > 100:
            return self.content[:100] + "..."
        return self.content