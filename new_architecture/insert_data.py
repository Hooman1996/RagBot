# insert_data.py

"""
Minimal Safe Data Insertion Script
====================================

Directly inserts test data into all databases:
- PostgreSQL  → users, collections, documents, chunks, embeddings metadata
- MinIO       → actual PDF files
- Qdrant      → embedding vectors

Chunk folder structure:
    chunks_root/
    ├── my_first_document/
    │   ├── my_first_document_0.txt
    │   ├── my_first_document_1.txt
    │   └── my_first_document_2.txt
    ├── second_document/
    │   ├── second_document_0.txt
    │   └── second_document_1.txt
    └── ...

Usage:
    python insert_data.py

Configuration:
    1. Replace PDF_FILES paths with your actual PDF file paths
    2. Replace CHUNKS_ROOT_DIR with your actual chunks folder path
    3. Run: python insert_data.py
"""

import os
from dotenv import load_dotenv

# Load variables from .env into os.environ
load_dotenv()

import sys
import json
import uuid
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import re
import bcrypt
import psycopg2
import psycopg2.extras
import httpx
from minio import Minio
from minio.error import S3Error
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.performance_config import PERFORMANCE_SETTINGS
from utils.tei_embedding_batches import TeiInsertionSession


# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

class Config:
    """Configuration"""

    # PostgreSQL
    # POSTGRES_HOST = "localhost"
    # POSTGRES_PORT = 5432
    # POSTGRES_DB = "hihelp_db"
    # POSTGRES_USER = "postgres"
    # POSTGRES_PASSWORD = "postgres"

    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "hihelp_db")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")



    # MinIO
    # MINIO_ENDPOINT = "localhost:9000"
    # MINIO_ACCESS_KEY = "minioadmin"
    # MINIO_SECRET_KEY = "minioadmin"
    # MINIO_SECURE = False
    # MINIO_BUCKET = "hihelp-documents"

    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_SECURE = os.getenv("MINIO_SECURE", False)
    MINIO_BUCKET = os.getenv("MINIO_BUCKET", "hihelp-documents")


    # Qdrant
    # QDRANT_HOST = "localhost"
    # QDRANT_PORT = 6333
    # QDRANT_COLLECTION = "hihelp_embeddings"
    # QDRANT_VECTOR_SIZE = 1024
    # QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = os.getenv("QDRANT_PORT", 6333)
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "hihelp_embeddings")
    QDRANT_VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", "1024"))
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


    TEI_EMBED_URL = os.getenv("TEI_EMBED_URL")

# ═══════════════════════════════════════════════════════════
# ↓↓↓ CONFIGURE YOUR PATHS HERE ↓↓↓
# ═══════════════════════════════════════════════════════════

# ── Root folder that contains ALL chunk subfolders ──────────
# Example: "/home/user/data/chunks"
# Structure inside:
#   chunks/
#   ├── my_first_document/
#   │   ├── my_first_document_0.txt
#   │   ├── my_first_document_1.txt
#   │   └── ...
#   ├── second_document/
#   │   ├── second_document_0.txt
#   │   └── ...
#   └── ...

# DATA_DIR = "/nvme/Chatbot/faq/data_insertion_chunks"  # ← REPLACE THIS
DATA_DIR = os.getenv("DATA_INSERTION_DIRECTORY")
# CHUNKS_ROOT_DIR = "/home/hooman/PycharmProjects/faq/data_insertion_chunks"  # ← REPLACE THIS

# ── Documents to upload ─────────────────────────────────────
# Each entry needs:
#   file_path  → full path to the PDF file
#   title      → display title (can be anything)
#   chunk_dir  → name of the subfolder inside CHUNKS_ROOT_DIR
#                (must match the folder name exactly)


DOCUMENTS = []
documents_directory = os.path.join(DATA_DIR, "DOCUMENTS")
CHUNKS_ROOT_DIR = os.path.join(DATA_DIR, "CHUNKS")

for filename in os.listdir(documents_directory):
    DOCUMENTS.append(
        {"file_path": os.path.join(documents_directory, filename),
         "chunk_dir": os.path.join(CHUNKS_ROOT_DIR, filename.split(".")[0]),
         "title":filename.split(".")[0],
         "owner": "admin",  # Must match a username below
        "collection": "Hi_Help"  # Must match a collection below
        }
    )


# DOCUMENTS = [
#     {
#         # ─── REPLACE THESE ──────────────────────────────────
#         "file_path": "/home/hooman/PycharmProjects/faq/General_FAQ.csv",
#         "chunk_dir": "/home/hooman/PycharmProjects/faq/data_insertion_chunks/General_FAQ",
#         # ────────────────────────────────────────────────────
#         "title": "General_FAQ",
#         "owner": "admin",  # Must match a username below
#         "collection": "Hi_Help",  # Must match a collection below
#
#     },
#     {
#         # ─── REPLACE THESE ──────────────────────────────────
#         "file_path": "/home/hooman/Downloads/RagBotData/شیوه نامه اجرایی تسهیلات کمک ودیعه مسکن.pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/شیوه نامه اجرایی تسهیلات کمک ودیعه مسکن",
#         # ────────────────────────────────────────────────────
#         "title": "شیوه نامه اجرایی تسهیلات کمک ودیعه مسکن",
#         "owner": "johndoe",
#         "collection": "Technical Manuals",
#
#     },
#     {
#         # ─── REPLACE THESE ──────────────────────────────────
#         "file_path": "/home/hooman/Downloads/RagBotData/شیوه نامه اجرایی تسهیلات قرض الحسنه اشتغال سازمان بهزیستی.pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/شیوه نامه اجرایی تسهیلات قرض الحسنه اشتغال سازمان بهزیستی",
#         # ────────────────────────────────────────────────────
#         "title": "شیوه نامه اجرایی تسهیلات قرض الحسنه اشتغال سازمان بهزیستی",
#         "owner": "johndoe",
#         "collection": "Technical Manuals",
#
#     },
#     {
#         # ─── REPLACE THESE ──────────────────────────────────
#         "file_path": "/home/hooman/Downloads/RagBotData/شیوه نامه اجرایی دستورالعمل افتتاح حساب سپرده ریالی برای اشخاص خارجی.pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/شیوه نامه اجرایی دستورالعمل افتتاح حساب سپرده ریالی برای اشخاص خارجی",
#         # ────────────────────────────────────────────────────
#         "title": "شیوه نامه اجرایی دستورالعمل افتتاح حساب سپرده ریالی برای اشخاص خارجی",
#         "owner": "admin",
#         "collection": "Company Policies",
#
#     },
#     {
#         # ─── REPLACE THESE ──────────────────────────────────
#         "file_path": "/home/hooman/Downloads/RagBotData/شیوه نامه امكان سنجی ارائه اطلاعات از بانك به مراجع ذی صلاح.pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/شیوه نامه امكان سنجی ارائه اطلاعات از بانك به مراجع ذی صلاح",
#         # ────────────────────────────────────────────────────
#         "title": "شیوه نامه امكان سنجی ارائه اطلاعات از بانك به مراجع ذی صلاح",
#         "owner": "admin",
#         "collection": "Company Policies",
#
#     },
#     {
#         # ─── REPLACE THESE ──────────────────────────────────
#         "file_path": "/home/hooman/Downloads/RagBotData/فرایند صدور بیمه نامه باربری (مرتبط با موضوع صدور حواله های ارزی ).pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/فرایند صدور بیمه نامه باربری",
#         # ────────────────────────────────────────────────────
#         "title": "فرایند صدور بیمه نامه باربری",
#         "owner": "admin",
#         "collection": "Company Policies",
#
#     },
#     {
#         # ─── REPLACE THESE ──────────────────────────────────
#         "file_path": "/home/hooman/Downloads/RagBotData/نحوه دسته‌بندی و بایگانی اسناد روزانه.pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/نحوه دسته‌بندی و بایگانی اسناد روزانه",
#         # ────────────────────────────────────────────────────
#         "title": "نحوه دسته‌بندی و بایگانی اسناد روزانه",
#         "owner": "admin",
#         "collection": "Company Policies",
#
#     },
# ]
#
# DOCUMENTS == DOCUMENTS_
# ═══════════════════════════════════════════════════════════
# ↑↑↑ END OF CONFIGURATION ↑↑↑
# ═══════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════
# TEST USERS
# ═══════════════════════════════════════════════════════════

USERS = [
    {
        "username": "admin",
        "email": "admin@example.com",
        "password": "Admin@123",
        "full_name": "System Administrator",
        "role": "admin",
        "is_active": True,
        "is_verified": True,
        "bio": "System administrator with full access",
        "settings": {
            "theme": "dark",
            "notifications": True,
            "language": "en"
        }
    },
    {
        "username": "johndoe",
        "email": "john.doe@example.com",
        "password": "john@123",
        "full_name": "John Doe",
        "role": "user",
        "is_active": True,
        "is_verified": True,
        "bio": "Regular user - Software Engineer",
        "settings": {
            "theme": "light",
            "notifications": True,
            "language": "en"
        }
    },
    {
        "username": "janesmith",
        "email": "jane.smith@example.com",
        "password": "jane@123",
        "full_name": "Jane Smith",
        "role": "user",
        "is_active": True,
        "is_verified": True,
        "bio": "Regular user - Data Scientist",
        "settings": {
            "theme": "light",
            "notifications": False,
            "language": "en"
        }
    },
    {
        "username": "moderator",
        "email": "moderator@example.com",
        "password": "mod@123",
        "full_name": "Content Moderator",
        "role": "moderator",
        "is_active": True,
        "is_verified": True,
        "bio": "Content moderator with review permissions",
        "settings": {
            "theme": "dark",
            "notifications": True,
            "language": "en"
        }
    },
    {
        "username": "alicejohnson",
        "email": "alice.johnson@example.com",
        "password": "alice@123",
        "full_name": "Alice Johnson",
        "role": "user",
        "is_active": True,
        "is_verified": False,
        "bio": "New user - awaiting email verification",
        "settings": {
            "theme": "light",
            "notifications": True,
            "language": "en"
        }
    },
]

# ═══════════════════════════════════════════════════════════
# TEST COLLECTIONS
# ═══════════════════════════════════════════════════════════

COLLECTIONS = [
    {
        "name": "Hi_Help",
        "description": "Hi_Help Data",
        "owner": "admin",
        "is_public": True,
    },
    # {
    #     "name": "Technical Manuals",
    #     "description": "Product and technical documentation",
    #     "owner": "johndoe",
    #     "is_public": False,
    # },
    # {
    #     "name": "Company Policies",
    #     "description": "Internal company policy documents",
    #     "owner": "admin",
    #     "is_public": False,
    # },
]


# ═══════════════════════════════════════════════════════════
# DATABASE CONNECTIONS
# ═══════════════════════════════════════════════════════════

class Connections:
    """Hold all database connections"""

    def __init__(self):
        self.pg = None
        self.minio = None
        self.qdrant = None

    def connect(self) -> bool:
        """Connect to all databases"""

        print()
        print("=" * 80)
        print("CONNECTING TO DATABASES")
        print("=" * 80)
        print()

        # ── PostgreSQL ──────────────────────────────────────
        print("→ PostgreSQL...")
        try:
            self.pg = psycopg2.connect(
                host=Config.POSTGRES_HOST,
                port=Config.POSTGRES_PORT,
                dbname=Config.POSTGRES_DB,
                user=Config.POSTGRES_USER,
                password=Config.POSTGRES_PASSWORD
            )
            print("  ✓ Connected")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            return False

        # ── MinIO ───────────────────────────────────────────
        print("→ MinIO...")
        try:
            self.minio = Minio(
                Config.MINIO_ENDPOINT,
                access_key=Config.MINIO_ACCESS_KEY,
                secret_key=Config.MINIO_SECRET_KEY,
                secure=Config.MINIO_SECURE
            )
            if not self.minio.bucket_exists(Config.MINIO_BUCKET):
                self.minio.make_bucket(Config.MINIO_BUCKET)
                print(f"  → Created bucket: {Config.MINIO_BUCKET}")
            print("  ✓ Connected")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            return False

        # ── Qdrant ──────────────────────────────────────────
        print("→ Qdrant...")
        try:
            self.qdrant = QdrantClient(
                host=Config.QDRANT_HOST,
                port=Config.QDRANT_PORT
            )
            collections = [
                c.name
                for c in self.qdrant.get_collections().collections
            ]
            if Config.QDRANT_COLLECTION not in collections:
                self.qdrant.create_collection(
                    collection_name=Config.QDRANT_COLLECTION,
                    vectors_config=VectorParams(
                        size=Config.QDRANT_VECTOR_SIZE,
                        distance=Distance.COSINE
                    )
                )
                print(f"  → Created collection: {Config.QDRANT_COLLECTION}")
            print("  ✓ Connected")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            return False

        print()
        print("✅ All databases connected")
        print()
        return True

    def close(self):
        """Close all connections"""
        if self.pg:
            self.pg.close()


# ═══════════════════════════════════════════════════════════
# CHUNK LOADER
# ═══════════════════════════════════════════════════════════

def load_chunks_from_folder(
        chunks_root: str,
        chunk_dir: str
) -> List[Tuple[int, str]]:
    """
    Load all chunk files from a document's subfolder
    in correct numerical order.

    Folder structure expected:
        chunks_root/
        └── chunk_dir/
            ├── chunk_dir_0.txt
            ├── chunk_dir_1.txt
            ├── chunk_dir_2.txt
            └── ...

    Args:
        chunks_root : Root folder containing all chunk subfolders
        chunk_dir   : Name of this document's chunk subfolder
                      (e.g. "my_first_document")

    Returns:
        List of (chunk_index, chunk_text) tuples sorted by index
    """

    folder_path = Path(chunks_root) / chunk_dir

    if not folder_path.exists():
        print(f"  ✗ Chunk folder not found: {folder_path}")
        return []

    if not folder_path.is_dir():
        print(f"  ✗ Not a directory: {folder_path}")
        return []

    # ── Collect all .txt files in this folder ────────────────
    # Expected pattern: chunk_dir_<number>.txt
    # Example: my_first_document_0.txt, my_first_document_1.txt

    chunk_files = []

    for file in folder_path.iterdir():

        if not file.is_file():
            continue

        # Accept .txt files only
        if file.suffix.lower() != ".txt":
            continue

        # Extract chunk index from filename
        # e.g. "my_first_document_7.txt" → stem = "my_first_document_7"
        stem = file.stem  # filename without extension

        # Split on last underscore to get the number
        # e.g. "my_first_document_7" → ["my_first_document", "7"]
        # parts = stem.split("/")[-1].split("_")[0]
        #
        # if len(parts) != 2:
        #     print(f"  ⚠️  Skipping unexpected filename: {file.name}")
        #     continue

        try:
            # chunk_index = int(parts[1])
            chunk_index = int(re.findall(r'\d+', stem)[0])
        except ValueError:
            print(f"  ⚠️  Skipping non-numeric index: {file.name}")
            continue

        chunk_files.append((chunk_index, file))

    if not chunk_files:
        print(f"  ✗ No valid chunk files found in: {folder_path}")
        return []

    # ── Sort by chunk index ──────────────────────────────────
    chunk_files.sort(key=lambda x: x[0])

    # ── Read file contents ───────────────────────────────────
    chunks = []

    for chunk_index, file_path in chunk_files:
        try:
            content = file_path.read_text(encoding="utf-8").strip()
            if content:
                chunks.append((chunk_index, content))
        except Exception as e:
            print(f"  ⚠️  Failed to read {file_path.name}: {e}")
            continue

    return chunks


def preview_chunk_folders(chunks_root: str):
    """
    Preview all chunk folders and their file counts
    before insertion.

    Args:
        chunks_root: Root folder containing all chunk subfolders
    """
    print()
    print("=" * 80)
    print("CHUNK FOLDER PREVIEW")
    print("=" * 80)
    print()

    root = Path(chunks_root)

    if not root.exists():
        print(f"  ✗ Root folder not found: {chunks_root}")
        print()
        return

    print(f"  Root: {chunks_root}")
    print()

    subfolders = sorted([f for f in root.iterdir() if f.is_dir()])

    if not subfolders:
        print("  ✗ No subfolders found")
        print()
        return

    total_chunks = 0

    for folder in subfolders:
        txt_files = sorted(
            [f for f in folder.iterdir() if f.is_file() and f.suffix == ".txt"],
            key=lambda f: int(f.stem.rsplit("_", 1)[-1])
            if f.stem.rsplit("_", 1)[-1].isdigit() else 0
        )

        count = len(txt_files)
        total_chunks += count

        # Show first and last file
        first = txt_files[0].name if txt_files else "—"
        last = txt_files[-1].name if txt_files else "—"

        print(f"  📁 {folder.name}")
        print(f"     Files : {count}")
        print(f"     First : {first}")
        print(f"     Last  : {last}")
        print()

    print(f"  Total folders : {len(subfolders)}")
    print(f"  Total chunks  : {total_chunks:,}")
    print()


# ═══════════════════════════════════════════════════════════
# STEP 1 — INSERT USERS
# ═══════════════════════════════════════════════════════════

def insert_users(pg) -> Dict[str, int]:
    """
    Insert users into PostgreSQL

    Returns:
        username → user_id mapping
    """
    print()
    print("=" * 80)
    print("STEP 1 — INSERTING USERS")
    print("=" * 80)
    print()

    user_ids = {}
    cursor = pg.cursor()

    for user in USERS:

        # Check if user already exists
        cursor.execute("""
                       SELECT id
                       FROM users
                       WHERE username = %s
                       """, (user["username"],))

        existing = cursor.fetchone()

        if existing:
            user_ids[user["username"]] = existing[0]
            print(f"  → Skipped (exists): {user['username']:<20} ID: {existing[0]}")
            continue

        # Hash password
        hashed = bcrypt.hashpw(
            user["password"].encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        now = datetime.utcnow()

        cursor.execute("""
                       INSERT INTO users (uuid, username, email, password_hash,
                                          full_name, role, is_active, is_verified,
                                          bio, settings, created_at, updated_at)
                       VALUES (gen_random_uuid()::text, %s, %s, %s,
                               %s, %s, %s, %s,
                               %s, %s, %s, %s) RETURNING id
                       """, (
                           user["username"],
                           user["email"],
                           hashed,
                           user["full_name"],
                           user["role"],
                           user["is_active"],
                           user["is_verified"],
                           user["bio"],
                           json.dumps(user["settings"]),
                           now,
                           now
                       ))

        user_id = cursor.fetchone()[0]
        user_ids[user["username"]] = user_id

        print(
            f"  ✓ Inserted: {user['username']:<20} "
            f"ID: {user_id:<5} "
            f"Role: {user['role']}"
        )

    pg.commit()
    cursor.close()

    print()
    print(f"  Total users: {len(user_ids)}")
    print()

    return user_ids


# ═══════════════════════════════════════════════════════════
# STEP 2 — INSERT COLLECTIONS
# ═══════════════════════════════════════════════════════════

def insert_collections(
        pg,
        user_ids: Dict[str, int]
) -> Dict[str, int]:
    """
    Insert collections into PostgreSQL

    Returns:
        collection_name → collection_id mapping
    """
    print()
    print("=" * 80)
    print("STEP 2 — INSERTING COLLECTIONS")
    print("=" * 80)
    print()

    collection_ids = {}
    cursor = pg.cursor()

    for col in COLLECTIONS:

        cursor.execute("""
                       SELECT id
                       FROM collections
                       WHERE name = %s
                       """, (col["name"],))

        existing = cursor.fetchone()

        if existing:
            collection_ids[col["name"]] = existing[0]
            print(f"  → Skipped (exists): {col['name']}")
            continue

        owner_id = user_ids.get(col["owner"])

        if not owner_id:
            print(f"  ✗ Owner not found: {col['owner']}")
            continue

        now = datetime.utcnow()

        cursor.execute("""
                       INSERT INTO collections (uuid, user_id, name, description,
                                                is_public, document_count, total_size,
                                                created_at, updated_at)
                       VALUES (gen_random_uuid()::text, %s, %s, %s,
                               %s, %s, %s,
                               %s, %s) RETURNING id
                       """, (
                           owner_id,
                           col["name"],
                           col["description"],
                           col["is_public"],
                           0,
                           0,
                           now,
                           now
                       ))

        col_id = cursor.fetchone()[0]
        collection_ids[col["name"]] = col_id

        print(f"  ✓ Inserted: {col['name']:<30} ID: {col_id}")

    pg.commit()
    cursor.close()

    print()
    print(f"  Total collections: {len(collection_ids)}")
    print()

    return collection_ids


# ═══════════════════════════════════════════════════════════
# STEP 3 — UPLOAD DOCUMENTS TO MINIO + INSERT TO POSTGRESQL
# ═══════════════════════════════════════════════════════════

def insert_documents(
        pg,
        minio,
        user_ids: Dict[str, int],
        collection_ids: Dict[str, int]
) -> Dict[str, int]:
    """
    Upload documents to MinIO and insert records into PostgreSQL

    Returns:
        document_title → document_id mapping
    """
    print()
    print("=" * 80)
    print("STEP 3 — UPLOADING DOCUMENTS")
    print("=" * 80)
    print()

    document_ids = {}
    cursor = pg.cursor()

    for doc in DOCUMENTS:

        file_path = doc["file_path"]

        print(f"  → Document: {doc['title']}")

        # ── Validate file ────────────────────────────────────
        if not os.path.exists(file_path):
            print(f"    ✗ File not found: {file_path}")
            print(f"    → Skipping")
            print()
            continue

        # ── Check if document already exists ─────────────────
        cursor.execute("""
                       SELECT id
                       FROM documents
                       WHERE title = %s
                       """, (doc["title"],))

        existing = cursor.fetchone()

        if existing:
            document_ids[doc["title"]] = existing[0]
            print(f"    → Skipped (exists) ID: {existing[0]}")
            print()
            continue

        path = Path(file_path)
        filename = path.name
        file_size = path.stat().st_size
        file_ext = path.suffix.lower()
        doc_uuid = str(uuid.uuid4())
        now = datetime.utcnow()
        owner_id = user_ids.get(doc["owner"])
        collection_id = collection_ids.get(doc["collection"])

        # ── Calculate SHA256 hash ────────────────────────────
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                sha256.update(block)
        file_hash = sha256.hexdigest()

        # ── Determine MIME type ──────────────────────────────
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

        # ── MinIO storage path ───────────────────────────────
        minio_path = (
            f"user_{owner_id}"
            f"/{now.year}/{now.month:02d}"
            f"/{doc_uuid}_{filename}"
        )

        print(f"    File      : {filename}")
        print(f"    Size      : {file_size:,} bytes")
        print(f"    MIME      : {mime_type}")
        print(f"    Hash      : {file_hash[:16]}...")
        print(f"    MinIO path: {minio_path}")

        # ── Upload to MinIO ──────────────────────────────────
        try:
            minio.fput_object(
                bucket_name=Config.MINIO_BUCKET,
                object_name=minio_path,
                file_path=file_path,
                content_type=mime_type
            )
            print(f"    ✓ Uploaded to MinIO")
        except S3Error as e:
            print(f"    ✗ MinIO upload failed: {e}")
            print()
            continue

        # ── Generate presigned URL ───────────────────────────
        try:
            presigned_url = minio.presigned_get_object(
                bucket_name=Config.MINIO_BUCKET,
                object_name=minio_path,
                expires=timedelta(days=7)
            )
        except Exception:
            presigned_url = None

        # ── Insert into PostgreSQL ───────────────────────────
        cursor.execute("""
                       INSERT INTO documents (uuid, user_id, collection_id,
                                              title, filename,
                                              file_path, file_url, file_size,
                                              file_type, mime_type, file_hash,
                                              status, processing_status,
                                              meta_data, created_at, updated_at)
                       VALUES (%s, %s, %s,
                               %s, %s,
                               %s, %s, %s,
                               %s, %s, %s,
                               %s, %s, %s,
                               %s, %s) RETURNING id
                       """, (
                           doc_uuid,
                           owner_id,
                           collection_id,
                           doc["title"],
                           filename,
                           minio_path,
                           presigned_url,
                           file_size,
                           file_ext.lstrip("."),
                           mime_type,
                           file_hash,
                           "pending",
                           "pending",
                           json.dumps({}),
                           now,
                           now
                       ))

        doc_id = cursor.fetchone()[0]
        document_ids[doc["title"]] = doc_id

        # ── Update collection stats ──────────────────────────
        if collection_id:
            cursor.execute("""
                           UPDATE collections
                           SET document_count = document_count + 1,
                               total_size     = total_size + %s,
                               updated_at     = %s
                           WHERE id = %s
                           """, (file_size, now, collection_id))

        pg.commit()

        print(f"    ✓ Inserted into PostgreSQL (ID: {doc_id})")
        print()

    cursor.close()

    print(f"  Total documents: {len(document_ids)}")
    print()

    return document_ids


# ═══════════════════════════════════════════════════════════
# STEP 4 — LOAD CHUNKS FROM FOLDERS + INSERT INTO POSTGRESQL
# ═══════════════════════════════════════════════════════════

def insert_chunks(
        pg,
        document_ids: Dict[str, int]
) -> Dict[str, List[int]]:
    """
    Load chunk files from folders and insert into PostgreSQL.

    Expected structure:
        CHUNKS_ROOT_DIR/
        └── <chunk_dir>/
            ├── <chunk_dir>_0.txt
            ├── <chunk_dir>_1.txt
            └── ...

    Returns:
        document_title → [chunk_id, ...] mapping
    """
    print()
    print("=" * 80)
    print("STEP 4 — INSERTING CHUNKS")
    print("=" * 80)
    print()

    all_chunk_ids = {}
    cursor = pg.cursor()

    for doc in DOCUMENTS:

        doc_title = doc["title"]
        chunk_dir = doc["chunk_dir"]
        doc_id = document_ids.get(doc_title)

        print(f"  → Document : {doc_title}")
        print(f"    Folder   : {chunk_dir}")

        if not doc_id:
            print(f"    ✗ Document ID not found — skipping")
            print()
            continue

        # ── Check if chunks already exist ────────────────────
        cursor.execute("""
                       SELECT id
                       FROM chunks
                       WHERE document_id = %s
                       ORDER BY chunk_index
                       """, (doc_id,))

        existing = cursor.fetchall()

        if existing:
            existing_ids = [r[0] for r in existing]
            all_chunk_ids[doc_title] = existing_ids
            print(f"    → Skipped (exists): {len(existing_ids)} chunks")
            print()
            continue

        # ── Load chunks from folder ──────────────────────────
        chunks = load_chunks_from_folder(CHUNKS_ROOT_DIR, chunk_dir)

        if not chunks:
            print(f"    ✗ No chunks loaded — skipping")
            print()
            continue

        print(f"    Chunks loaded: {len(chunks)}")

        # ── Insert chunks into PostgreSQL ────────────────────
        chunk_ids = []
        now = datetime.utcnow()

        for chunk_index, content in chunks:
            cursor.execute("""
                           INSERT INTO chunks (uuid, document_id, content,
                                               chunk_index, chunk_type,
                                               token_count, char_count,
                                               start_char, end_char,
                                               meta_data, created_at, updated_at)
                           VALUES (gen_random_uuid()::text, %s, %s,
                                   %s, %s,
                                   %s, %s,
                                   %s, %s,
                                   %s, %s, %s) RETURNING id
                           """, (
                               doc_id,
                               content,
                               chunk_index,
                               "text",
                               len(content.split()),  # Approximate token count
                               len(content),  # Char count
                               0,  # start_char (positional tracking)
                               len(content),  # end_char
                               json.dumps({
                                   "source_file": f"{chunk_dir}_{chunk_index}.txt",
                                   "folder": chunk_dir
                               }),
                               now,
                               now
                           ))

            chunk_id = cursor.fetchone()[0]
            chunk_ids.append(chunk_id)

        pg.commit()

        all_chunk_ids[doc_title] = chunk_ids

        # ── Update document processing status ────────────────
        cursor.execute("""
                       UPDATE documents
                       SET processing_status = 'chunked',
                           updated_at        = %s
                       WHERE id = %s
                       """, (datetime.utcnow(), doc_id))

        pg.commit()

        print(f"    ✓ Inserted {len(chunk_ids)} chunks")
        print()

    cursor.close()

    total = sum(len(v) for v in all_chunk_ids.values())
    print(f"  Total chunks inserted: {total:,}")
    print()

    return all_chunk_ids


# ═══════════════════════════════════════════════════════════
# STEP 5 — GENERATE EMBEDDINGS + STORE IN QDRANT + POSTGRESQL
# ═══════════════════════════════════════════════════════════

def insert_embeddings(
        pg,
        qdrant,
        document_ids: Dict[str, int],
        all_chunk_ids: Dict[str, List[int]],
        embedding_session: TeiInsertionSession,
):
    """
    Generate embeddings for all chunks and store in:
    - Qdrant     → vectors with metadata payload
    - PostgreSQL → embedding metadata and lineage
    """
    print()
    print("=" * 80)
    print("STEP 5 — GENERATING & INSERTING EMBEDDINGS")
    print("=" * 80)
    print()

    cursor = pg.cursor()

    from parsivar import Normalizer, Tokenizer, FindStems
    normalizer = Normalizer()


    for doc_title, chunk_ids in all_chunk_ids.items():

        doc_id = document_ids.get(doc_title)

        print(f"  → Document : {doc_title}")
        print(f"    Chunks   : {len(chunk_ids)}")

        if not doc_id:
            print(f"    ✗ Document ID not found — skipping")
            print()
            continue

        # ── Check if embeddings already exist ────────────────
        cursor.execute("""
                       SELECT COUNT(*)
                       FROM embeddings
                       WHERE document_id = %s
                       """, (doc_id,))

        existing_count = cursor.fetchone()[0]

        if existing_count > 0:
            print(f"    → Skipped ({existing_count} embeddings exist)")
            print()
            continue

        # ── Fetch chunk content from PostgreSQL ──────────────
        cursor.execute("""
                       SELECT id, chunk_index, content
                       FROM chunks
                       WHERE document_id = %s
                       ORDER BY chunk_index ASC
                       """, (doc_id,))

        rows = cursor.fetchall()
        c_ids = [r[0] for r in rows]
        c_indices = [r[1] for r in rows]
        c_texts = [r[2] for r in rows]

        if not c_texts:
            print(f"    ✗ No chunks found in DB — skipping")
            print()
            continue

        # ── Generate embeddings ──────────────────────────────
        print(f"    → Generating embeddings...")

        normalized_c_texts = []

        for i, text in enumerate(c_texts):
            normalized_c_texts.append(normalizer.normalize(text))

        c_texts = normalized_c_texts

        # Stored vectors intentionally use raw document semantics. Do not add a
        # document prompt without rebuilding and reevaluating the collection.
        vectors = embedding_session.embed_documents(
            c_texts,
            c_ids,
        )

        print(f"    ✓ Generated {len(vectors)} vectors (dim: {len(vectors[0])})")

        # ── Upload to Qdrant ─────────────────────────────────
        print(f"    → Uploading to Qdrant...")

        points = [
            PointStruct(
                id=c_id,
                vector=vector,
                payload={
                    "chunk_id": c_id,
                    "chunk_index": c_index,
                    "document_id": doc_id,
                    "document": doc_title
                }
            )
            for c_id, c_index, vector in zip(c_ids, c_indices, vectors)
        ]

        # qdrant.upsert(
        #     collection_name=Config.QDRANT_COLLECTION,
        #     points=points,
        # )

        # Example for upload_points
        qdrant.upload_points(
            collection_name=Config.QDRANT_COLLECTION,
            points=points,  # A list of PointStruct objects
            batch_size=256,  # Optimal batch size for internal processing
            parallel=2,  # Number of parallel threads
        )

        print(f"    ✓ Uploaded {len(points)} vectors to Qdrant")

        # ── Save metadata to PostgreSQL ──────────────────────
        print(f"    → Saving metadata to PostgreSQL...")

        now = datetime.utcnow()

        for c_id, vector in zip(c_ids, vectors):
            cursor.execute("""
                           INSERT INTO embeddings (uuid, chunk_id, document_id,
                                                   vector, vector_dimension,
                                                   model_name, model_version,
                                                   vector_db_id, vector_db_collection,
                                                   status, created_at, updated_at)
                           VALUES (gen_random_uuid()::text, %s, %s,
                                   %s, %s,
                                   %s, %s,
                                   %s, %s,
                                   %s, %s, %s)
                           """, (
                               c_id,
                               doc_id,
                               json.dumps(vector),
                               len(vector),
                               # Config.EMBEDDING_MODEL,
                               "Jinna-V3",
                               "1.0",
                               str(c_id),  # Qdrant point ID = chunk_id
                               Config.QDRANT_COLLECTION,
                               "active",
                               now,
                               now
                           ))

        pg.commit()

        # ── Mark document as completed ───────────────────────
        cursor.execute("""
                       UPDATE documents
                       SET status            = 'completed',
                           processing_status = 'completed',
                           processed_at      = %s,
                           updated_at        = %s
                       WHERE id = %s
                       """, (now, now, doc_id))

        pg.commit()

        print(f"    ✓ Saved {len(c_ids)} embedding records")
        print()

    cursor.close()


def batch_upsert(client, collection_name, points, batch_size=50):
    """Upserts points in batches."""
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        try:
            client.upsert(
                collection_name=collection_name,
                points=batch
            )
            print(f"Successfully upserted batch {i // batch_size + 1}")
        except Exception as e:
            print(f"Error upserting batch {i // batch_size + 1}: {e}")


# ═══════════════════════════════════════════════════════════
# STEP 6 — VERIFY
# ═══════════════════════════════════════════════════════════

def verify(pg, qdrant):
    """Verify all data was inserted correctly"""

    print()
    print("=" * 80)
    print("STEP 6 — VERIFICATION")
    print("=" * 80)
    print()

    cursor = pg.cursor()

    # ── PostgreSQL ───────────────────────────────────────────
    print("  PostgreSQL:")

    tables = [
        "users",
        "collections",
        "documents",
        "chunks",
        "embeddings"
    ]

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"    {table:<20} {count:>8,} records")

    print()

    # ── Per-document breakdown ───────────────────────────────
    print("  Per-document breakdown:")

    cursor.execute("""
                   SELECT d.title,
                          d.status,
                          d.processing_status,
                          COUNT(DISTINCT c.id) AS chunks,
                          COUNT(DISTINCT e.id) AS embeddings
                   FROM documents d
                            LEFT JOIN chunks c ON c.document_id = d.id
                            LEFT JOIN embeddings e ON e.document_id = d.id
                   GROUP BY d.id, d.title, d.status, d.processing_status
                   ORDER BY d.id
                   """)

    rows = cursor.fetchall()

    print(
        f"    {'Title':<30} "
        f"{'Status':<12} "
        f"{'Chunks':>8} "
        f"{'Embeds':>8}"
    )
    print("    " + "─" * 62)

    for row in rows:
        title, status, proc_status, chunks, embeds = row
        print(
            f"    {title[:28]:<30} "
            f"{proc_status:<12} "
            f"{chunks:>8,} "
            f"{embeds:>8,}"
        )

    print()

    # ── Qdrant ───────────────────────────────────────────────
    print("  Qdrant:")
    try:
        info = qdrant.get_collection(Config.QDRANT_COLLECTION)
        print(f"    {'Collection':<20} {Config.QDRANT_COLLECTION}")
        print(f"    {'Vectors':<20} {info.vectors_count:>8,}")
    except Exception as e:
        print(f"    ✗ Failed: {e}")

    print()

    cursor.close()


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    if not isinstance(Config.TEI_EMBED_URL, str) or not Config.TEI_EMBED_URL.strip():
        raise ValueError("TEI_EMBED_URL must be present")
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "DATA INSERTION SCRIPT".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    # ── Preview chunk folders before starting ────────────────
    preview_chunk_folders(CHUNKS_ROOT_DIR)

    # ── Confirm before proceeding ────────────────────────────
    print("  Proceed with insertion? (yes/no): ", end="")
    answer = input().strip().lower()

    if answer != "yes":
        print("\n  Cancelled.\n")
        return

    # ── Connect ──────────────────────────────────────────────
    db = Connections()
    if not db.connect():
        print("❌ Connection failed. Exiting.")
        return

    try:
        # ── Step 1: Users ─────────────────────────────────────
        user_ids = insert_users(db.pg)

        # ── Step 2: Collections ───────────────────────────────
        collection_ids = insert_collections(db.pg, user_ids)

        # ── Step 3: Documents → MinIO + PostgreSQL ────────────
        document_ids = insert_documents(
            db.pg,
            db.minio,
            user_ids,
            collection_ids
        )

        # ── Step 4: Chunks → PostgreSQL ───────────────────────
        all_chunk_ids = insert_chunks(db.pg, document_ids)

        # ── Step 5: Embeddings → Qdrant + PostgreSQL ──────────
        timeout = httpx.Timeout(
            connect=PERFORMANCE_SETTINGS.tei_http_connect_timeout_seconds,
            read=PERFORMANCE_SETTINGS.tei_http_read_timeout_seconds,
            write=PERFORMANCE_SETTINGS.tei_http_write_timeout_seconds,
            pool=PERFORMANCE_SETTINGS.tei_http_pool_timeout_seconds,
        )
        limits = httpx.Limits(
            max_connections=PERFORMANCE_SETTINGS.tei_http_max_connections,
            max_keepalive_connections=(
                PERFORMANCE_SETTINGS.tei_http_max_keepalive_connections
            ),
            keepalive_expiry=(
                PERFORMANCE_SETTINGS.tei_http_keepalive_expiry_seconds
            ),
        )
        with TeiInsertionSession(
            base_url=Config.TEI_EMBED_URL,
            timeout=timeout,
            limits=limits,
            expected_dimension=Config.QDRANT_VECTOR_SIZE,
            batch_size=PERFORMANCE_SETTINGS.tei_embed_insert_batch_size,
        ) as embedding_session:
            insert_embeddings(
                db.pg,
                db.qdrant,
                document_ids,
                all_chunk_ids,
                embedding_session,
            )

        # ── Step 6: Verify ────────────────────────────────────
        # verify(db.pg, db.qdrant)

        print()
        print("╔" + "═" * 78 + "╗")
        print("║" + " " * 78 + "║")
        print("║" + "✅  ALL DATA INSERTED SUCCESSFULLY".center(78) + "║")
        print("║" + " " * 78 + "║")
        print("╚" + "═" * 78 + "╝")
        print()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled\n")
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback

        traceback.print_exc()
