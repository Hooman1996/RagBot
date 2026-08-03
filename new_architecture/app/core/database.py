# app/core/database.py

"""
Database Core Module - Minimal Safe Version
============================================

Handles database connections and session management for:
- PostgreSQL (SQLAlchemy)
- MinIO (Object Storage)
- Qdrant (Vector Database)

Usage:
    from app.core.database import get_db, get_minio_client, get_qdrant_client

    # PostgreSQL
    db = next(get_db())
    users = db.query(User).all()

    # MinIO
    minio = get_minio_client()
    minio.list_buckets()

    # Qdrant
    qdrant = get_qdrant_client()
    qdrant.get_collections()
"""

import os
from dotenv import load_dotenv
from typing import Generator, Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, event, pool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from minio import Minio
from minio.error import S3Error

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams


# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

class DatabaseConfig:
    """Database configuration"""

    # PostgreSQL
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "rag_db")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")

    # MinIO
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "documents")

    # Qdrant
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "hihelp_embeddings")
    QDRANT_VECTOR_SIZE: int = int(os.getenv("QDRANT_VECTOR_SIZE", "384"))
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY",)

    # SQLAlchemy settings
    SQLALCHEMY_POOL_SIZE: int = int(os.getenv("SQLALCHEMY_POOL_SIZE", "5"))
    SQLALCHEMY_MAX_OVERFLOW: int = int(os.getenv("SQLALCHEMY_MAX_OVERFLOW", "10"))
    SQLALCHEMY_POOL_TIMEOUT: int = int(os.getenv("SQLALCHEMY_POOL_TIMEOUT", "30"))
    SQLALCHEMY_POOL_RECYCLE: int = int(os.getenv("SQLALCHEMY_POOL_RECYCLE", "3600"))
    SQLALCHEMY_ECHO: bool = os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true"

    @property
    def DATABASE_URL(self) -> str:
        """Get PostgreSQL database URL"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """Get async PostgreSQL database URL"""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


# Global config instance
config = DatabaseConfig()

# ═══════════════════════════════════════════════════════════
# POSTGRESQL - SQLALCHEMY
# ═══════════════════════════════════════════════════════════

# Create declarative base
Base = declarative_base()

# Create engine
engine = create_engine(
    config.DATABASE_URL,
    pool_size=config.SQLALCHEMY_POOL_SIZE,
    max_overflow=config.SQLALCHEMY_MAX_OVERFLOW,
    pool_timeout=config.SQLALCHEMY_POOL_TIMEOUT,
    pool_recycle=config.SQLALCHEMY_POOL_RECYCLE,
    pool_pre_ping=True,  # Enable connection health checks
    echo=config.SQLALCHEMY_ECHO,
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# ═══════════════════════════════════════════════════════════
# POSTGRESQL - SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════

def get_db() -> Generator[Session, None, None]:
    """
    Get database session (for dependency injection)

    Usage:
        from app.core.database import get_db

        def my_function(db: Session = Depends(get_db)):
            users = db.query(User).all()

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """
    Get database session as context manager

    Usage:
        from app.core.database import get_db_context

        with get_db_context() as db:
            users = db.query(User).all()

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """
    Initialize database (create all tables)

    Usage:
        from app.core.database import init_db
        init_db()
    """
    # Import all models to register them with Base
    from ..models.user import User
    from ..models.collection import Collection
    from ..models.document import Document
    from ..models.chunk import Chunk
    from ..models.embedding import Embedding
    from ..models.query import Query
    from ..models.chat_session import ChatSession
    from ..models.feedback import Feedback

    # Create all tables
    Base.metadata.create_all(bind=engine)


def drop_db():
    """
    Drop all database tables (USE WITH CAUTION!)

    Usage:
        from app.core.database import drop_db
        drop_db()
    """
    Base.metadata.drop_all(bind=engine)


# ═══════════════════════════════════════════════════════════
# MINIO - OBJECT STORAGE
# ═══════════════════════════════════════════════════════════

# Global MinIO client
_minio_client: Optional[Minio] = None


def get_minio_client() -> Minio:
    """
    Get MinIO client (singleton)

    Usage:
        from app.core.database import get_minio_client

        minio = get_minio_client()
        minio.list_buckets()

    Returns:
        MinIO client instance
    """
    global _minio_client

    if _minio_client is None:
        _minio_client = Minio(
            config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE
        )

        # Ensure bucket exists
        try:
            if not _minio_client.bucket_exists(config.MINIO_BUCKET):
                _minio_client.make_bucket(config.MINIO_BUCKET)
                print(f"Created MinIO bucket: {config.MINIO_BUCKET}")
        except S3Error as e:
            print(f"Warning: MinIO bucket check failed: {e}")

    return _minio_client


def init_minio():
    """
    Initialize MinIO (ensure bucket exists)

    Usage:
        from app.core.database import init_minio
        init_minio()
    """
    client = get_minio_client()

    try:
        if not client.bucket_exists(config.MINIO_BUCKET):
            client.make_bucket(config.MINIO_BUCKET)
            print(f"✓ Created MinIO bucket: {config.MINIO_BUCKET}")
        else:
            print(f"✓ MinIO bucket exists: {config.MINIO_BUCKET}")
    except S3Error as e:
        print(f"✗ MinIO initialization failed: {e}")
        raise


# ═══════════════════════════════════════════════════════════
# QDRANT - VECTOR DATABASE
# ═══════════════════════════════════════════════════════════

# Global Qdrant client
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """
    Get Qdrant client (singleton)

    Usage:
        from app.core.database import get_qdrant_client

        qdrant = get_qdrant_client()
        qdrant.get_collections()

    Returns:
        Qdrant client instance
    """
    global _qdrant_client

    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            host=config.QDRANT_HOST,
            port=config.QDRANT_PORT,
            api_key=os.getenv("QDRANT_API_KEY"),
        )

    return _qdrant_client


def init_qdrant():
    """
    Initialize Qdrant (ensure collection exists)

    Usage:
        from app.core.database import init_qdrant
        init_qdrant()
    """
    client = get_qdrant_client()

    try:
        # Get existing collections
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        # Create collection if it doesn't exist
        if config.QDRANT_COLLECTION not in collection_names:
            client.create_collection(
                collection_name=config.QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=config.QDRANT_VECTOR_SIZE,
                    distance=Distance.COSINE
                )
            )
            print(f"✓ Created Qdrant collection: {config.QDRANT_COLLECTION}")
        else:
            print(f"✓ Qdrant collection exists: {config.QDRANT_COLLECTION}")

    except Exception as e:
        print(f"✗ Qdrant initialization failed: {e}")
        raise


# ═══════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════

def init_all_databases():
    """
    Initialize all databases

    Usage:
        from app.core.database import init_all_databases
        init_all_databases()
    """
    print()
    print("=" * 80)
    print("INITIALIZING ALL DATABASES")
    print("=" * 80)
    print()

    # PostgreSQL
    print("→ PostgreSQL...")
    try:
        init_db()
        print("  ✓ PostgreSQL initialized")
    except Exception as e:
        print(f"  ✗ PostgreSQL failed: {e}")
        raise

    # MinIO
    print("→ MinIO...")
    try:
        init_minio()
    except Exception as e:
        print(f"  ✗ MinIO failed: {e}")
        raise

    # Qdrant
    print("→ Qdrant...")
    try:
        init_qdrant()
    except Exception as e:
        print(f"  ✗ Qdrant failed: {e}")
        raise

    print()
    print("✅ All databases initialized successfully")
    print()


def check_connections():
    """
    Check all database connections

    Usage:
        from app.core.database import check_connections
        check_connections()

    Returns:
        Dictionary with connection status
    """
    results = {
        'postgresql': False,
        'minio': False,
        'qdrant': False
    }

    print()
    print("=" * 80)
    print("CHECKING DATABASE CONNECTIONS")
    print("=" * 80)
    print()

    # PostgreSQL
    print("→ PostgreSQL...")
    try:
        with get_db_context() as db:
            db.execute("SELECT 1")
        results['postgresql'] = True
        print("  ✓ PostgreSQL connected")
    except Exception as e:
        print(f"  ✗ PostgreSQL failed: {e}")

    # MinIO
    print("→ MinIO...")
    try:
        client = get_minio_client()
        client.list_buckets()
        results['minio'] = True
        print("  ✓ MinIO connected")
    except Exception as e:
        print(f"  ✗ MinIO failed: {e}")

    # Qdrant
    print("→ Qdrant...")
    try:
        client = get_qdrant_client()
        client.get_collections()
        results['qdrant'] = True
        print("  ✓ Qdrant connected")
    except Exception as e:
        print(f"  ✗ Qdrant failed: {e}")

    print()

    all_connected = all(results.values())

    if all_connected:
        print("✅ All databases connected successfully")
    else:
        print("⚠️  Some databases failed to connect")
        for db, status in results.items():
            if not status:
                print(f"   ✗ {db}")

    print()

    return results


# ═══════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════

def close_all_connections():
    """
    Close all database connections

    Usage:
        from app.core.database import close_all_connections
        close_all_connections()
    """
    global _minio_client, _qdrant_client

    print()
    print("→ Closing database connections...")

    # Close SQLAlchemy engine
    engine.dispose()

    # Reset clients
    _minio_client = None
    _qdrant_client = None

    print("  ✓ All connections closed")
    print()


# ═══════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════

def get_db_stats() -> dict:
    """
    Get database statistics

    Returns:
        Dictionary with database stats
    """
    with get_db_context() as db:
        from ..models.user import User
        from ..models.document import Document
        from ..models.chunk import Chunk
        from ..models.embedding import Embedding
        from ..models.query import Query

        return {
            'users': db.query(User).count(),
            'documents': db.query(Document).count(),
            'chunks': db.query(Chunk).count(),
            'embeddings': db.query(Embedding).count(),
            'queries': db.query(Query).count(),
        }


def reset_database():
    """
    Reset database (drop and recreate all tables)
    USE WITH EXTREME CAUTION!

    Usage:
        from app.core.database import reset_database
        reset_database()
    """
    print()
    print("⚠️  WARNING: This will delete ALL data!")
    print()

    response = input("Type 'RESET DATABASE' to confirm: ")

    if response != 'RESET DATABASE':
        print("Cancelled")
        return

    print()
    print("→ Dropping all tables...")
    drop_db()

    print("→ Creating all tables...")
    init_db()

    print("✓ Database reset complete")
    print()


# ═══════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════

__all__ = [
    # Base
    'Base',
    'engine',
    'SessionLocal',

    # Config
    'DatabaseConfig',
    'config',

    # PostgreSQL
    'get_db',
    'get_db_context',
    'init_db',
    'drop_db',

    # MinIO
    'get_minio_client',
    'init_minio',

    # Qdrant
    'get_qdrant_client',
    'init_qdrant',

    # Initialization
    'init_all_databases',
    'check_connections',
    'close_all_connections',

    # Utilities
    'get_db_stats',
    'reset_database',
]