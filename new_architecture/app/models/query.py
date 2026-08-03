# app/models/query.py

"""
Query Model - Minimal Safe Version
===================================
User queries and responses for RAG system
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..core.database import Base


class Query(Base):
    """Query model - user questions and AI responses"""

    __tablename__ = "queries"

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

    chat_session_id = Column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    # Optional: group queries into chat sessions

    # ═══════════════════════════════════════════════════════════
    # QUERY DATA
    # ═══════════════════════════════════════════════════════════

    query_text = Column(Text, nullable=False)
    # The user's question/query

    response_text = Column(Text)
    # The AI's response

    # ═══════════════════════════════════════════════════════════
    # QUERY METADATA
    # ═══════════════════════════════════════════════════════════

    query_type = Column(String(50), default="question")
    # Types: question, command, clarification, feedback, etc.

    language = Column(String(10), default="en")
    # Language code: en, es, fr, etc.

    # ═══════════════════════════════════════════════════════════
    # RETRIEVAL DATA
    # ═══════════════════════════════════════════════════════════

    retrieved_chunks = Column(JSON, default=list)
    # List of chunk IDs that were retrieved for this query
    # Example: [123, 456, 789]

    retrieved_documents = Column(JSON, default=list)
    # List of document IDs that chunks came from
    # Example: [10, 20]

    retrieval_method = Column(String(50))
    # Method used: semantic_search, keyword_search, hybrid, etc.

    # ═══════════════════════════════════════════════════════════
    # PERFORMANCE METRICS
    # ═══════════════════════════════════════════════════════════

    response_time = Column(Float)
    # Response time in seconds

    token_count = Column(Integer)
    # Number of tokens in query + response

    relevance_score = Column(Float)
    # Average relevance score of retrieved chunks (0-1)

    # ═══════════════════════════════════════════════════════════
    # MODEL INFO
    # ═══════════════════════════════════════════════════════════

    model_name = Column(String(100))
    # LLM model used: gpt-4, gpt-3.5-turbo, claude-3, etc.

    embedding_model = Column(String(100))
    # Embedding model used for retrieval

    temperature = Column(Float)
    # Temperature setting used

    # ═══════════════════════════════════════════════════════════
    # STATUS & FLAGS
    # ═══════════════════════════════════════════════════════════

    status = Column(String(50), default="completed")
    # Status: pending, processing, completed, failed

    is_helpful = Column(Integer)
    # User feedback: 1 (helpful), 0 (not helpful), null (no feedback)

    has_sources = Column(Integer, default=0)
    # Whether response includes source citations

    # ═══════════════════════════════════════════════════════════
    # ADDITIONAL METADATA
    # ═══════════════════════════════════════════════════════════

    meta_data = Column(JSON, default=dict)
    # Additional metadata: context, filters, settings, etc.

    error_message = Column(Text)
    # Error message if query failed

    # ═══════════════════════════════════════════════════════════
    # TIMESTAMPS
    # ═══════════════════════════════════════════════════════════

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
    # When the response was completed

    # ═══════════════════════════════════════════════════════════
    # RELATIONSHIPS - MINIMAL
    # ═══════════════════════════════════════════════════════════

    user = relationship(
        "User",
        back_populates="queries"
    )

    # Uncomment if you have ChatSession model
    # chat_session = relationship(
    #     "ChatSession",
    #     back_populates="queries"
    # )

    # ═══════════════════════════════════════════════════════════
    # INDEXES
    # ═══════════════════════════════════════════════════════════

    __table_args__ = (
        Index('idx_user_created', 'user_id', 'created_at'),
        Index('idx_session_created', 'chat_session_id', 'created_at'),
        Index('idx_status', 'status'),
    )

    def __repr__(self):
        preview = self.query_text[:50] + "..." if len(self.query_text) > 50 else self.query_text
        return f"<Query(id={self.id}, user_id={self.user_id}, query='{preview}')>"

    @property
    def query_preview(self):
        """Get preview of query (first 100 chars)"""
        if len(self.query_text) > 100:
            return self.query_text[:100] + "..."
        return self.query_text

    @property
    def response_preview(self):
        """Get preview of response (first 100 chars)"""
        if self.response_text and len(self.response_text) > 100:
            return self.response_text[:100] + "..."
        return self.response_text or ""

    @property
    def retrieved_chunk_count(self):
        """Get number of retrieved chunks"""
        if isinstance(self.retrieved_chunks, list):
            return len(self.retrieved_chunks)
        return 0