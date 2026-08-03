# app/models/user.py

"""
User Model - Minimal Safe Version
==================================
Only essential fields and relationships
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..core.database import Base


class User(Base):
    """User model - minimal version with only essential relationships"""

    __tablename__ = "users"

    # ═══════════════════════════════════════════════════════════
    # PRIMARY KEY
    # ═══════════════════════════════════════════════════════════

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))

    # ═══════════════════════════════════════════════════════════
    # AUTHENTICATION
    # ═══════════════════════════════════════════════════════════

    email = Column(String(255), unique=True, index=True, nullable=True)
    username = Column(String(100), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)

    # ═══════════════════════════════════════════════════════════
    # PROFILE
    # ═══════════════════════════════════════════════════════════

    full_name = Column(String(255))

    # NEW: Added national_code as String(20) which translates to VARCHAR(20) in Postgres
    national_code = Column(String(20), unique=True, index=True, nullable=True)

    bio = Column(Text)
    avatar_url = Column(String(500))

    # ═══════════════════════════════════════════════════════════
    # ROLE & STATUS
    # ═══════════════════════════════════════════════════════════

    role = Column(String(50), default="user", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # ═══════════════════════════════════════════════════════════
    # SETTINGS
    # ═══════════════════════════════════════════════════════════

    settings = Column(JSON, default=dict)

    # ═══════════════════════════════════════════════════════════
    # TIMESTAMPS
    # ═══════════════════════════════════════════════════════════

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime)

    # ═══════════════════════════════════════════════════════════
    # RELATIONSHIPS - MINIMAL (Only core tables)
    # ═══════════════════════════════════════════════════════════

    documents = relationship(
        "Document",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    collections = relationship(
        "Collection",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    chat_sessions = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    queries = relationship(
        "Query",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    feedbacks = relationship(
        "Feedback",
        foreign_keys="[Feedback.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    reviewed_feedbacks = relationship(
        "Feedback",
        foreign_keys="[Feedback.reviewed_by]",
        back_populates="reviewer",
        lazy="dynamic"
    )

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}', national_code='{self.national_code}')>"