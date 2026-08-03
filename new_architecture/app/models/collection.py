# app/models/collection.py

"""
Collection Model - Minimal Safe Version
========================================
Document collections/folders
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, BigInteger, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..core.database import Base


class Collection(Base):
    """Collection model - groups of documents"""

    __tablename__ = "collections"

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

    # ═══════════════════════════════════════════════════════════
    # COLLECTION INFO
    # ═══════════════════════════════════════════════════════════

    name = Column(String(255), nullable=False)
    description = Column(Text)

    # ═══════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════

    document_count = Column(Integer, default=0, nullable=False)
    total_size = Column(BigInteger, default=0, nullable=False)  # Total size in bytes

    # ═══════════════════════════════════════════════════════════
    # SETTINGS
    # ═══════════════════════════════════════════════════════════

    is_public = Column(Boolean, default=False, nullable=False)
    settings = Column(JSON, default=dict)

    # ═══════════════════════════════════════════════════════════
    # TIMESTAMPS
    # ═══════════════════════════════════════════════════════════

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ═══════════════════════════════════════════════════════════
    # RELATIONSHIPS - MINIMAL
    # ═══════════════════════════════════════════════════════════

    user = relationship(
        "User",
        back_populates="collections"
    )

    documents = relationship(
        "Document",
        back_populates="collection",
        lazy="dynamic"
    )

    def __repr__(self):
        return f"<Collection(id={self.id}, name='{self.name}', docs={self.document_count})>"

    @property
    def total_size_mb(self):
        """Get total size in MB"""
        if self.total_size:
            return round(self.total_size / (1024 * 1024), 2)
        return 0