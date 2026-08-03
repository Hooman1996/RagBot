# app/models/feedback.py

"""
Feedback Model - Minimal Safe Version
======================================
User feedback on query responses
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..core.database import Base


class Feedback(Base):
    """Feedback model - user ratings and comments on query responses"""

    __tablename__ = "feedbacks"

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

    query_id = Column(
        Integer,
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True  # One feedback per query
    )

    # ═══════════════════════════════════════════════════════════
    # RATING
    # ═══════════════════════════════════════════════════════════

    rating = Column(Integer, nullable=False)
    # Rating scale: 1-5 stars
    # 1 = Very Poor, 2 = Poor, 3 = Average, 4 = Good, 5 = Excellent

    is_helpful = Column(Boolean)
    # Simple boolean: True (helpful), False (not helpful), None (not rated)

    # ═══════════════════════════════════════════════════════════
    # FEEDBACK CATEGORIES
    # ═══════════════════════════════════════════════════════════

    accuracy = Column(Integer)
    # Accuracy rating: 1-5 (how accurate was the response)

    relevance = Column(Integer)
    # Relevance rating: 1-5 (how relevant was the response)

    completeness = Column(Integer)
    # Completeness rating: 1-5 (how complete was the response)

    clarity = Column(Integer)
    # Clarity rating: 1-5 (how clear was the response)

    # ═══════════════════════════════════════════════════════════
    # FEEDBACK TEXT
    # ═══════════════════════════════════════════════════════════

    comment = Column(Text)
    # User's text comment/feedback

    improvement_suggestions = Column(Text)
    # Suggestions for improvement

    # ═══════════════════════════════════════════════════════════
    # FEEDBACK TYPE
    # ═══════════════════════════════════════════════════════════

    feedback_type = Column(String(50), default="rating")
    # Types: rating, comment, bug_report, feature_request, other

    sentiment = Column(String(20))
    # Sentiment: positive, neutral, negative (auto-detected or manual)

    # ═══════════════════════════════════════════════════════════
    # ISSUES & FLAGS
    # ═══════════════════════════════════════════════════════════

    has_issues = Column(Boolean, default=False)
    # Whether user reported issues

    issue_types = Column(JSON, default=list)
    # List of issue types: ["incorrect_info", "missing_sources", "irrelevant", etc.]

    # ═══════════════════════════════════════════════════════════
    # METADATA
    # ═══════════════════════════════════════════════════════════

    meta_data = Column(JSON, default=dict)
    # Additional metadata: device, browser, session_info, etc.

    # ═══════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════

    status = Column(String(50), default="submitted")
    # Status: submitted, reviewed, resolved, archived

    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Admin/moderator who reviewed this feedback

    reviewed_at = Column(DateTime)
    # When feedback was reviewed

    resolution_notes = Column(Text)
    # Notes from reviewer

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
        foreign_keys=[user_id],
        backref="feedbacks"
    )

    query = relationship(
        "Query",
        backref="feedback",
        uselist=False  # One-to-one relationship
    )

    reviewer = relationship(
        "User",
        foreign_keys=[reviewed_by],
        backref="reviewed_feedbacks"
    )

    # ═══════════════════════════════════════════════════════════
    # INDEXES
    # ═══════════════════════════════════════════════════════════

    __table_args__ = (
        Index('idx_user_rating', 'user_id', 'rating'),
        Index('idx_query_rating', 'query_id', 'rating'),
        Index('idx_rating', 'rating'),
        Index('idx_is_helpful', 'is_helpful'),
        # Index('idx_status', 'status'),
        Index('idx_created', 'created_at'),
    )

    def __repr__(self):
        return f"<Feedback(id={self.id}, query_id={self.query_id}, rating={self.rating}, helpful={self.is_helpful})>"

    @property
    def average_score(self):
        """Calculate average score across all rating categories"""
        scores = [
            self.accuracy,
            self.relevance,
            self.completeness,
            self.clarity
        ]
        valid_scores = [s for s in scores if s is not None]

        if valid_scores:
            return round(sum(valid_scores) / len(valid_scores), 2)

        return self.rating if self.rating else None

    @property
    def is_positive(self):
        """Check if feedback is positive"""
        if self.is_helpful is not None:
            return self.is_helpful

        if self.rating:
            return self.rating >= 4

        return None

    @property
    def is_negative(self):
        """Check if feedback is negative"""
        if self.is_helpful is not None:
            return not self.is_helpful

        if self.rating:
            return self.rating <= 2

        return None