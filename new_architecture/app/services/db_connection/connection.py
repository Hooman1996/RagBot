# ═══════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════

# Database clients
import psycopg2
import psycopg2.extras
import os
from minio import Minio
from minio.error import S3Error
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from dotenv import load_dotenv
load_dotenv()

# Services
import bcrypt
from ...config import Config
# ═══════════════════════════════════════════════════════════
# 1. DATABASE CONNECTION SERVICE
# ═══════════════════════════════════════════════════════════

class DatabaseConnections:
    """Manage connections to all databases"""

    def __init__(self):
        self.postgres_conn = None
        self.minio_client = None
        self.qdrant_client = None

    def connect_all(self) -> bool:
        """Connect to all databases"""
        print()
        print("=" * 80)
        print("CONNECTING TO DATABASES")
        print("=" * 80)
        print()

        # PostgreSQL
        print("→ Connecting to PostgreSQL...")
        try:

            self.postgres_conn = psycopg2.connect(
                host=Config.POSTGRES_HOST,
                port=Config.POSTGRES_PORT,
                dbname=Config.POSTGRES_DB,
                user=Config.POSTGRES_USER,
                password=Config.POSTGRES_PASSWORD,
                connect_timeout=5,
                options="-c statement_timeout=10000 -c lock_timeout=3000",
            )
            print(f"  ✓ PostgreSQL connected")
        except Exception as e:
            print(f"  ❌ PostgreSQL connection failed: {e}")
            return False

        # MinIO
        print("→ Connecting to MinIO...")
        try:

            self.minio_client = Minio(
                Config.MINIO_ENDPOINT,
                access_key=Config.MINIO_ACCESS_KEY,
                secret_key=Config.MINIO_SECRET_KEY,
                secure=Config.MINIO_SECURE
            )

            # Ensure bucket exists
            if not self.minio_client.bucket_exists(Config.MINIO_BUCKET):
                self.minio_client.make_bucket(Config.MINIO_BUCKET)
                print(f"  → Created bucket: {Config.MINIO_BUCKET}")

            print(f"  ✓ MinIO connected")
        except Exception as e:
            print(f"  ❌ MinIO connection failed: {e}")
            return False

        # Qdrant
        print("→ Connecting to Qdrant...")
        try:
            self.qdrant_client = QdrantClient(
                host=Config.QDRANT_HOST,
                port=Config.QDRANT_PORT,
                # api_key="NDBp255",
                api_key=os.getenv("QDRANT_API_KEY"),
                https = Config.QDRANT_HTTPS,
                timeout=10.0,
                # https=False
            )


            # Check if collection exists, create if not
            collections = self.qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]

            if Config.QDRANT_COLLECTION not in collection_names:
                self.qdrant_client.create_collection(
                    collection_name=Config.QDRANT_COLLECTION,
                    vectors_config=VectorParams(
                        size=Config.QDRANT_VECTOR_SIZE,
                        distance=Distance.COSINE
                    )
                )
                print(f"  → Created collection: {Config.QDRANT_COLLECTION}")

            print(f"  ✓ Qdrant connected")
        except Exception as e:
            print(f"  ❌ Qdrant connection failed: {e}")
            print(os.getenv("QDRANT_HTTPS"))
            return False

        print()
        print("✅ All databases connected successfully")
        print()

        return True

    def close_all(self):
        """Close all connections"""
        if self.postgres_conn:
            self.postgres_conn.close()
            self.postgres_conn = None
        if self.qdrant_client:
            self.qdrant_client.close()
            self.qdrant_client = None
        if self.minio_client:
            # MinIO owns an urllib3 PoolManager. Clearing it closes pooled
            # sockets; no object is used concurrently during shutdown.
            self.minio_client._http.clear()
            self.minio_client = None


