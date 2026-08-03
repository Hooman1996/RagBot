# app/models/document.py

"""
Document Model - Minimal Safe Version
======================================
Only essential fields and relationships
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, BigInteger, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..core.database import Base


class Document(Base):
    """Document model - minimal version with only essential relationships"""

    __tablename__ = "documents"

    # ═══════════════════════════════════════════════════════════
    # PRIMARY KEY
    # ═══════════════════════════════════════════════════════════

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))

    # ═══════════════════════════════════════════════════════════
    # FOREIGN KEYS
    # ═══════════════════════════════════════════════════════════

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    collection_id = Column(
        Integer,
        ForeignKey("collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # ═══════════════════════════════════════════════════════════
    # DOCUMENT INFO
    # ═══════════════════════════════════════════════════════════

    title = Column(String(500), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(1000), nullable=False)  # Path in MinIO
    file_url = Column(String(1000))  # Presigned URL or public URL

    # ═══════════════════════════════════════════════════════════
    # FILE METADATA
    # ═══════════════════════════════════════════════════════════

    file_size = Column(BigInteger)  # Size in bytes
    file_type = Column(String(50))  # pdf, text, markdown, etc.
    mime_type = Column(String(100))  # application/pdf, text/plain, etc.
    file_hash = Column(String(64), index=True)  # SHA-256 hash for deduplication

    # ═══════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════

    status = Column(String(50), default="pending", nullable=False)
    # Status values: pending, uploaded, processing, completed, failed

    processing_status = Column(String(50))
    # Processing status: pending, extracting, chunking, embedding, completed, failed

    # ═══════════════════════════════════════════════════════════
    # ADDITIONAL METADATA
    # ═══════════════════════════════════════════════════════════

    meta_data = Column(JSON, default=dict)
    # Store any additional metadata: page_count, language, author, etc.

    # ═══════════════════════════════════════════════════════════
    # TIMESTAMPS
    # ═══════════════════════════════════════════════════════════

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime)  # When processing completed

    # ═══════════════════════════════════════════════════════════
    # RELATIONSHIPS - MINIMAL
    # ═══════════════════════════════════════════════════════════

    # Parent relationships
    user = relationship(
        "User",
        back_populates="documents"
    )

    collection = relationship(
        "Collection",
        back_populates="documents"
    )

    # Child relationships
    chunks = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="dynamic"  # Don't load unless explicitly accessed
    )

    def __repr__(self):
        return f"<Document(id={self.id}, title='{self.title}', status='{self.status}')>"

    @property
    def chunk_count(self):
        """Get number of chunks (if loaded)"""
        try:
            return self.chunks.count()
        except:
            return 0

    @property
    def file_size_mb(self):
        """Get file size in MB"""
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0