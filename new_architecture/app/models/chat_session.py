# app/models/chat_session.py

"""
ChatSession Model - Minimal Safe Version
=========================================
Chat conversation sessions
"""

from .query import Query
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean, Float, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..core.database import Base


class ChatSession(Base):
    """ChatSession model - conversation sessions"""

    __tablename__ = "chat_sessions"

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
    # SESSION INFO
    # ═══════════════════════════════════════════════════════════

    title = Column(String(255))
    # Auto-generated or user-provided title

    description = Column(Text)
    # Optional description

    # ═══════════════════════════════════════════════════════════
    # SESSION SETTINGS
    # ═══════════════════════════════════════════════════════════

    model_name = Column(String(100))
    # Default model for this session

    temperature = Column(Float, default=0.1)
    # Default temperature

    settings = Column(JSON, default=dict)
    # Additional settings: max_tokens, top_p, etc.

    # ═══════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════

    query_count = Column(Integer, default=0)
    # Number of queries in this session

    total_tokens = Column(Integer, default=0)
    # Total tokens used in this session

    # ═══════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════

    status = Column(String(50), default="active")
    # Status: active, archived, deleted

    is_pinned = Column(Boolean, default=False)
    # Whether session is pinned

    # ═══════════════════════════════════════════════════════════
    # METADATA
    # ═══════════════════════════════════════════════════════════

    meta_data = Column(JSON, default=dict)
    # Additional metadata

    # ═══════════════════════════════════════════════════════════
    # TIMESTAMPS
    # ═══════════════════════════════════════════════════════════

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_activity_at = Column(DateTime, default=datetime.utcnow)
    # Last time a query was made in this session

    # ═══════════════════════════════════════════════════════════
    # RELATIONSHIPS - MINIMAL
    # ═══════════════════════════════════════════════════════════

    user = relationship(
        "User",
        back_populates="chat_sessions"
    )

    queries = relationship(
        "Query",
        back_populates="chat_session",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="Query.created_at"
    )

    def __repr__(self):
        return f"<ChatSession(id={self.id}, user_id={self.user_id}, title='{self.title}', queries={self.query_count})>"

    @property
    def first_query(self):
        """Get first query in session"""
        return self.queries.first()

    @property
    def last_query(self):
        """Get last query in session"""
        return self.queries.order_by(Query.created_at.desc()).first()