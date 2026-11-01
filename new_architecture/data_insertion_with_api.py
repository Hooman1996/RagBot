# insert_data.py

"""
Minimal Safe Data Insertion Script
====================================

Directly inserts test data into all databases:
- PostgreSQL  ? users, collections, documents, chunks, embeddings metadata
- MinIO       ? actual PDF files
- Qdrant      ? embedding vectors

Chunk folder structure:
    chunks_root/
    +-- my_first_document/
    ¦   +-- my_first_document_0.txt
    ¦   +-- my_first_document_1.txt
    ¦   +-- my_first_document_2.txt
    +-- second_document/
    ¦   +-- second_document_0.txt
    ¦   +-- second_document_1.txt
    +-- ...

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

import argparse
import contextlib
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
from qdrant_client.models import Distance, PointIdsList, VectorParams, PointStruct

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.performance_config import PERFORMANCE_SETTINGS
from utils.tei_embedding_batches import TeiInsertionSession
from new_architecture.knowledge_sources import (
    discover_chunk_files,
    discover_knowledge_sources,
)


# -----------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------

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
    # MINIO_SECURE = False
    # MINIO_BUCKET = "hihelp-documents"

    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
    MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
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


# -----------------------------------------------------------
# ??? CONFIGURE YOUR PATHS HERE ???
# -----------------------------------------------------------

# -- Root folder that contains ALL chunk subfolders ----------
# Example: "/home/user/data/chunks"
# Structure inside:
#   chunks/
#   +-- my_first_document/
#   ¦   +-- my_first_document_0.txt
#   ¦   +-- my_first_document_1.txt
#   ¦   +-- ...
#   +-- second_document/
#   ¦   +-- second_document_0.txt
#   ¦   +-- ...
#   +-- ...

# DATA_DIR = "/nvme/Chatbot/faq/data_insertion_chunks"  # ? REPLACE THIS
DATA_DIR = os.getenv("DATA_INSERTION_DIRECTORY")  # ? REPLACE THIS
# CHUNKS_ROOT_DIR = "/home/hooman/PycharmProjects/faq/data_insertion_chunks"  # ? REPLACE THIS

# -- Documents to upload -------------------------------------
# Each entry needs:
#   file_path  ? full path to the PDF file
#   title      ? display title (can be anything)
#   chunk_dir  ? name of the subfolder inside CHUNKS_ROOT_DIR
#                (must match the folder name exactly)


INSERT_ONLY = False
SOURCE_NAME = None

documents_directory = os.path.join(DATA_DIR, "DOCUMENTS") if DATA_DIR else None
CHUNKS_ROOT_DIR = os.path.join(DATA_DIR, "CHUNKS") if DATA_DIR else None

DOCUMENTS = []  # Discovered only after CLI source selection.



# DOCUMENTS = [
#     {
#         # --- REPLACE THESE ----------------------------------
#         "file_path": "/home/hooman/PycharmProjects/faq/General_FAQ.csv",
#         "chunk_dir": "/home/hooman/PycharmProjects/faq/data_insertion_chunks/General_FAQ",
#         # ----------------------------------------------------
#         "title": "General_FAQ",
#         "owner": "admin",  # Must match a username below
#         "collection": "Hi_Help",  # Must match a collection below
#
#     },
#     {
#         # --- REPLACE THESE ----------------------------------
#         "file_path": "/home/hooman/Downloads/RagBotData/???? ???? ?????? ??????? ??? ????? ????.pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/???? ???? ?????? ??????? ??? ????? ????",
#         # ----------------------------------------------------
#         "title": "???? ???? ?????? ??????? ??? ????? ????",
#         "owner": "johndoe",
#         "collection": "Technical Manuals",
#
#     },
#     {
#         # --- REPLACE THESE ----------------------------------
#         "file_path": "/home/hooman/Downloads/RagBotData/???? ???? ?????? ??????? ??? ?????? ?????? ?????? ???????.pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/???? ???? ?????? ??????? ??? ?????? ?????? ?????? ???????",
#         # ----------------------------------------------------
#         "title": "???? ???? ?????? ??????? ??? ?????? ?????? ?????? ???????",
#         "owner": "johndoe",
#         "collection": "Technical Manuals",
#
#     },
#     {
#         # --- REPLACE THESE ----------------------------------
#         "file_path": "/home/hooman/Downloads/RagBotData/???? ???? ?????? ?????????? ?????? ???? ????? ????? ???? ????? ?????.pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/???? ???? ?????? ?????????? ?????? ???? ????? ????? ???? ????? ?????",
#         # ----------------------------------------------------
#         "title": "???? ???? ?????? ?????????? ?????? ???? ????? ????? ???? ????? ?????",
#         "owner": "admin",
#         "collection": "Company Policies",
#
#     },
#     {
#         # --- REPLACE THESE ----------------------------------
#         "file_path": "/home/hooman/Downloads/RagBotData/???? ???? ????? ???? ????? ??????? ?? ???? ?? ????? ?? ????.pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/???? ???? ????? ???? ????? ??????? ?? ???? ?? ????? ?? ????",
#         # ----------------------------------------------------
#         "title": "???? ???? ????? ???? ????? ??????? ?? ???? ?? ????? ?? ????",
#         "owner": "admin",
#         "collection": "Company Policies",
#
#     },
#     {
#         # --- REPLACE THESE ----------------------------------
#         "file_path": "/home/hooman/Downloads/RagBotData/?????? ???? ???? ???? ?????? (????? ?? ????? ???? ????? ??? ???? ).pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/?????? ???? ???? ???? ??????",
#         # ----------------------------------------------------
#         "title": "?????? ???? ???? ???? ??????",
#         "owner": "admin",
#         "collection": "Company Policies",
#
#     },
#     {
#         # --- REPLACE THESE ----------------------------------
#         "file_path": "/home/hooman/Downloads/RagBotData/???? ????????? ? ??????? ????? ??????.pdf",
#         "chunk_dir": "/home/hooman/PycharmProjects/RegAssist/data_insertion_chunks/???? ????????? ? ??????? ????? ??????",
#         # ----------------------------------------------------
#         "title": "???? ????????? ? ??????? ????? ??????",
#         "owner": "admin",
#         "collection": "Company Policies",
#
#     },
# ]
#
# DOCUMENTS == DOCUMENTS_
# -----------------------------------------------------------
# ??? END OF CONFIGURATION ???
# -----------------------------------------------------------


# -----------------------------------------------------------
# TEST USERS
# -----------------------------------------------------------

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

# -----------------------------------------------------------
# TEST COLLECTIONS
# -----------------------------------------------------------

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


# -----------------------------------------------------------
# DATABASE CONNECTIONS
# -----------------------------------------------------------

class Connections:
    """Hold all database connections"""

    def __init__(self):
        self.pg = None
        self.minio = None
        self.qdrant = None

    def connect(self, insert_only=False) -> bool:
        """Connect to all databases"""

        print()
        print("=" * 80)
        print("CONNECTING TO DATABASES")
        print("=" * 80)
        print()

        # -- PostgreSQL --------------------------------------
        print("? PostgreSQL...")
        try:
            self.pg = psycopg2.connect(
                host=Config.POSTGRES_HOST,
                port=Config.POSTGRES_PORT,
                dbname=Config.POSTGRES_DB,
                user=Config.POSTGRES_USER,
                password=Config.POSTGRES_PASSWORD
            )
            print("  ? Connected")
        except Exception as e:
            if insert_only:
                raise InsertOnlyRefusal("Service connection or existing storage prerequisite failed") from None
            print(f"  ? Failed: {e}")
            return False

        # -- MinIO -------------------------------------------
        print("? MinIO...")
        try:
            self.minio = Minio(
                Config.MINIO_ENDPOINT,
                access_key=Config.MINIO_ACCESS_KEY,
                secret_key=Config.MINIO_SECRET_KEY,
                secure=Config.MINIO_SECURE
            )
            if not self.minio.bucket_exists(Config.MINIO_BUCKET):
                if insert_only:
                    raise RuntimeError("Configured bucket must already exist")
                self.minio.make_bucket(Config.MINIO_BUCKET)
                print(f"  ? Created bucket: {Config.MINIO_BUCKET}")
            print("  ? Connected")
        except Exception as e:
            if insert_only:
                raise InsertOnlyRefusal("Service connection or existing storage prerequisite failed") from None
            print(f"  ? Failed: {e}")
            return False

        # -- Qdrant ------------------------------------------
        print("? Qdrant...")
        try:
            self.qdrant = QdrantClient(
                host=Config.QDRANT_HOST,
                port=Config.QDRANT_PORT,
                api_key = Config.QDRANT_API_KEY,
                https = False
            )
            collections = [
                c.name
                for c in self.qdrant.get_collections().collections
            ]
            if Config.QDRANT_COLLECTION not in collections:
                if insert_only:
                    raise RuntimeError("Configured vector collection must already exist")
                self.qdrant.create_collection(
                    collection_name=Config.QDRANT_COLLECTION,
                    vectors_config=VectorParams(
                        size=Config.QDRANT_VECTOR_SIZE,
                        distance=Distance.COSINE
                    )
                )
                print(f"  ? Created collection: {Config.QDRANT_COLLECTION}")
            print("  ? Connected")
        except Exception as e:
            if insert_only:
                raise InsertOnlyRefusal("Service connection or existing storage prerequisite failed") from None
            print(f"  ? Failed: {e}")
            return False

        print()
        print("? All databases connected")
        print()
        return True

    def close(self):
        """Close all connections"""
        if self.pg:
            self.pg.close()


# -----------------------------------------------------------
# CHUNK LOADER
# -----------------------------------------------------------

def load_chunks_from_folder(
        chunks_root: str,
        chunk_dir: str
) -> List[Tuple[int, str]]:
    """
    Load all chunk files from a document's subfolder
    in correct numerical order.

    Folder structure expected:
        chunks_root/
        +-- chunk_dir/
            +-- chunk_dir_0.txt
            +-- chunk_dir_1.txt
            +-- chunk_dir_2.txt
            +-- ...

    Args:
        chunks_root : Root folder containing all chunk subfolders
        chunk_dir   : Name of this document's chunk subfolder
                      (e.g. "my_first_document")

    Returns:
        List of (chunk_index, chunk_text) tuples sorted by index
    """

    folder_path = Path(chunks_root) / chunk_dir

    if not folder_path.exists():
        print(f"  ? Chunk folder not found: {folder_path}")
        return []

    if not folder_path.is_dir():
        print(f"  ? Not a directory: {folder_path}")
        return []

    chunk_files = [
        (int(file.stem.rsplit("_", 1)[1]), file)
        for file in discover_chunk_files(folder_path)
    ]

    if not chunk_files:
        print(f"  ? No valid chunk files found in: {folder_path}")
        return []

    # -- Sort by chunk index ----------------------------------
    chunk_files.sort(key=lambda x: x[0])

    # -- Read file contents -----------------------------------
    chunks = []

    for chunk_index, file_path in chunk_files:
        try:
            content = file_path.read_text(encoding="utf-8").strip()
            if content:
                chunks.append((chunk_index, content))
        except Exception as e:
            print(f"  ??  Failed to read {file_path.name}: {e}")
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
        print(f"  ? Root folder not found: {chunks_root}")
        print()
        return

    print(f"  Root: {chunks_root}")
    print()

    subfolders = sorted([f for f in root.iterdir() if f.is_dir()
                         and (SOURCE_NAME is None or f.name == SOURCE_NAME)])

    if not subfolders:
        print("  ? No subfolders found")
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

        print(f"  ?? {folder.name}")
        print(f"     Files : {count}")
        print(f"     First : {first}")
        print(f"     Last  : {last}")
        print()

    print(f"  Total folders : {len(subfolders)}")
    print(f"  Total chunks  : {total_chunks:,}")
    print()


# -----------------------------------------------------------
# STEP 1 — INSERT USERS
# -----------------------------------------------------------

def insert_users(pg) -> Dict[str, int]:
    """
    Insert users into PostgreSQL

    Returns:
        username ? user_id mapping
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
            print(f"  ? Skipped (exists): {user['username']:<20} ID: {existing[0]}")
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
            f"  ? Inserted: {user['username']:<20} "
            f"ID: {user_id:<5} "
            f"Role: {user['role']}"
        )

    pg.commit()
    cursor.close()

    print()
    print(f"  Total users: {len(user_ids)}")
    print()

    return user_ids


# -----------------------------------------------------------
# STEP 2 — INSERT COLLECTIONS
# -----------------------------------------------------------

def insert_collections(
        pg,
        user_ids: Dict[str, int]
) -> Dict[str, int]:
    """
    Insert collections into PostgreSQL

    Returns:
        collection_name ? collection_id mapping
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
            print(f"  ? Skipped (exists): {col['name']}")
            continue

        owner_id = user_ids.get(col["owner"])

        if not owner_id:
            print(f"  ? Owner not found: {col['owner']}")
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

        print(f"  ? Inserted: {col['name']:<30} ID: {col_id}")

    pg.commit()
    cursor.close()

    print()
    print(f"  Total collections: {len(collection_ids)}")
    print()

    return collection_ids


# -----------------------------------------------------------
# STEP 3 — UPLOAD DOCUMENTS TO MINIO + INSERT TO POSTGRESQL
# -----------------------------------------------------------

def insert_documents(
        pg,
        minio,
        user_ids: Dict[str, int],
        collection_ids: Dict[str, int]
) -> Dict[str, int]:
    """
    Upload documents to MinIO and insert records into PostgreSQL

    Returns:
        document_title ? document_id mapping
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

        print(f"  ? Document: {doc['title']}")

        # -- Validate file ------------------------------------
        if not os.path.isfile(file_path) or os.path.getsize(file_path) == 0:
            print(f"    ? Missing or empty source file: {file_path}")
            print(f"    ? Skipping")
            print()
            continue

        valid_chunks = discover_chunk_files(
            Path(CHUNKS_ROOT_DIR) / doc["chunk_dir"]
        )
        if not valid_chunks:
            print("    ? No valid chunks for source — skipping")
            print()
            continue

        # -- Check if document already exists -----------------
        cursor.execute("""
                       SELECT id
                       FROM documents
                       WHERE title = %s
                       """, (doc["title"],))

        existing = cursor.fetchone()

        if existing:
            if INSERT_ONLY:
                raise InsertOnlyRefusal("Document title already exists")
            document_ids[doc["title"]] = existing[0]
            print(f"    ? Skipped (exists) ID: {existing[0]}")
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

        # -- Calculate SHA256 hash ----------------------------
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                sha256.update(block)
        file_hash = sha256.hexdigest()

        # -- Determine MIME type ------------------------------
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

        # -- MinIO storage path -------------------------------
        minio_prefix = os.getenv("MINIO_KNOWLEDGE_PREFIX", "").strip("/")
        minio_path = (
            (f"{minio_prefix}/" if minio_prefix else "")
            + f"user_{owner_id}"
            f"/{now.year}/{now.month:02d}"
            f"/{doc_uuid}_{filename}"
        )

        print(f"    File      : {filename}")
        print(f"    Size      : {file_size:,} bytes")
        print(f"    MIME      : {mime_type}")
        print(f"    Hash      : {file_hash[:16]}...")
        print(f"    MinIO path: {minio_path}")

        if INSERT_ONLY:
            require_object_absent(minio, minio_path)

        # -- Upload to MinIO ----------------------------------
        try:
            minio.fput_object(
                bucket_name=Config.MINIO_BUCKET,
                object_name=minio_path,
                file_path=file_path,
                content_type=mime_type
            )
            print(f"    ? Uploaded to MinIO")
        except S3Error as e:
            raise RuntimeError("MinIO knowledge upload failed") from e

        # -- Generate presigned URL ---------------------------
        try:
            presigned_url = minio.presigned_get_object(
                bucket_name=Config.MINIO_BUCKET,
                object_name=minio_path,
                expires=timedelta(days=7)
            )
        except Exception:
            presigned_url = None

        # -- Insert into PostgreSQL ---------------------------
        try:
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

            # -- Update collection stats ----------------------
            if collection_id:
                cursor.execute("""
                           UPDATE collections
                           SET document_count = document_count + 1,
                               total_size     = total_size + %s,
                               updated_at     = %s
                           WHERE id = %s
                               """, (file_size, now, collection_id))

            pg.commit()
        except Exception:
            pg.rollback()
            if not INSERT_ONLY:
                minio.remove_object(Config.MINIO_BUCKET, minio_path)
            raise

        print(f"    ? Inserted into PostgreSQL (ID: {doc_id})")
        print()

    cursor.close()

    print(f"  Total documents: {len(document_ids)}")
    print()

    return document_ids


# -----------------------------------------------------------
# STEP 4 — LOAD CHUNKS FROM FOLDERS + INSERT INTO POSTGRESQL
# -----------------------------------------------------------

def insert_chunks(
        pg,
        document_ids: Dict[str, int]
) -> Dict[str, List[int]]:
    """
    Load chunk files from folders and insert into PostgreSQL.

    Expected structure:
        CHUNKS_ROOT_DIR/
        +-- <chunk_dir>/
            +-- <chunk_dir>_0.txt
            +-- <chunk_dir>_1.txt
            +-- ...

    Returns:
        document_title ? [chunk_id, ...] mapping
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

        print(f"  ? Document : {doc_title}")
        print(f"    Folder   : {chunk_dir}")

        if not doc_id:
            print(f"    ? Document ID not found — skipping")
            print()
            continue

        # -- Check if chunks already exist --------------------
        cursor.execute("""
                       SELECT id
                       FROM chunks
                       WHERE document_id = %s
                       ORDER BY chunk_index
                       """, (doc_id,))

        existing = cursor.fetchall()

        if existing:
            if INSERT_ONLY:
                raise InsertOnlyRefusal("Unexpected existing chunks")
            existing_ids = [r[0] for r in existing]
            all_chunk_ids[doc_title] = existing_ids
            print(f"    ? Skipped (exists): {len(existing_ids)} chunks")
            print()
            continue

        # -- Load chunks from folder --------------------------
        chunks = load_chunks_from_folder(CHUNKS_ROOT_DIR, chunk_dir)

        if not chunks:
            print(f"    ? No chunks loaded — skipping")
            print()
            continue

        print(f"    Chunks loaded: {len(chunks)}")

        # -- Insert chunks into PostgreSQL --------------------
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

        # -- Update document processing status ----------------
        cursor.execute("""
                       UPDATE documents
                       SET processing_status = 'chunked',
                           updated_at        = %s
                       WHERE id = %s
                       """, (datetime.utcnow(), doc_id))

        pg.commit()

        print(f"    ? Inserted {len(chunk_ids)} chunks")
        print()

    cursor.close()

    total = sum(len(v) for v in all_chunk_ids.values())
    print(f"  Total chunks inserted: {total:,}")
    print()

    return all_chunk_ids


# -----------------------------------------------------------
# STEP 5 — GENERATE EMBEDDINGS + STORE IN QDRANT + POSTGRESQL
# -----------------------------------------------------------

def insert_embeddings(
        pg,
        qdrant,
        document_ids: Dict[str, int],
        all_chunk_ids: Dict[str, List[int]],
        embedding_session: TeiInsertionSession,
):
    """
    Generate embeddings for all chunks and store in:
    - Qdrant     ? vectors with metadata payload
    - PostgreSQL ? embedding metadata and lineage
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

        print(f"  ? Document : {doc_title}")
        print(f"    Chunks   : {len(chunk_ids)}")

        if not doc_id:
            print(f"    ? Document ID not found — skipping")
            print()
            continue

        # -- Check if embeddings already exist ----------------
        cursor.execute("""
                       SELECT COUNT(*)
                       FROM embeddings
                       WHERE document_id = %s
                       """, (doc_id,))

        existing_count = cursor.fetchone()[0]

        if existing_count > 0:
            if INSERT_ONLY:
                raise InsertOnlyRefusal("Unexpected existing embeddings")
            print(f"    ? Skipped ({existing_count} embeddings exist)")
            print()
            continue

        # -- Fetch chunk content from PostgreSQL --------------
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
            print(f"    ? No chunks found in DB — skipping")
            print()
            continue

        if INSERT_ONLY:
            require_vectors_absent(qdrant, c_ids)

        # -- Generate embeddings ------------------------------
        print(f"    ? Generating embeddings...")

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

        if INSERT_ONLY and len(vectors) != len(c_ids):
            raise InsertOnlyRefusal("Incomplete embedding generation")

        print(f"    ? Generated {len(vectors)} vectors (dim: {len(vectors[0])})")

        # -- Upload to Qdrant ---------------------------------
        print(f"    ? Uploading to Qdrant...")

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
        if INSERT_ONLY:
            require_vectors_absent(qdrant, c_ids)
        qdrant.upload_points(
            collection_name=Config.QDRANT_COLLECTION,
            points=points,  # A list of PointStruct objects
            batch_size=256,  # Optimal batch size for internal processing
            parallel=2,  # Number of parallel threads
            **({"wait": True} if INSERT_ONLY else {}),
        )

        print(f"    ? Uploaded {len(points)} vectors to Qdrant")

        # -- Save metadata to PostgreSQL ----------------------
        print(f"    ? Saving metadata to PostgreSQL...")

        now = datetime.utcnow()

        try:
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

            # -- Mark document as completed -------------------
            cursor.execute("""
                           UPDATE documents
                           SET status            = 'completed',
                               processing_status = 'completed',
                               processed_at      = %s,
                               updated_at        = %s
                           WHERE id = %s
                           """, (now, now, doc_id))

            pg.commit()
        except Exception:
            pg.rollback()
            if not INSERT_ONLY:
                qdrant.delete(
                    collection_name=Config.QDRANT_COLLECTION,
                    points_selector=PointIdsList(points=c_ids),
                    wait=True,
                )
            raise

        print(f"    ? Saved {len(c_ids)} embedding records")
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


# -----------------------------------------------------------
# STEP 6 — VERIFY
# -----------------------------------------------------------

def verify(pg, qdrant):
    """Verify all data was inserted correctly"""

    print()
    print("=" * 80)
    print("STEP 6 — VERIFICATION")
    print("=" * 80)
    print()

    cursor = pg.cursor()

    # -- PostgreSQL -------------------------------------------
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

    # -- Per-document breakdown -------------------------------
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
    print("    " + "-" * 62)

    for row in rows:
        title, status, proc_status, chunks, embeds = row
        print(
            f"    {title[:28]:<30} "
            f"{proc_status:<12} "
            f"{chunks:>8,} "
            f"{embeds:>8,}"
        )

    print()

    # -- Qdrant -----------------------------------------------
    print("  Qdrant:")
    try:
        info = qdrant.get_collection(Config.QDRANT_COLLECTION)
        print(f"    {'Collection':<20} {Config.QDRANT_COLLECTION}")
        print(f"    {'Vectors':<20} {info.vectors_count:>8,}")
    except Exception as e:
        print(f"    ? Failed: {e}")

    print()

    cursor.close()


# -----------------------------------------------------------
# MAIN
# -----------------------------------------------------------

def run_import(*, yes=False, preflight_only=False):
    if not DOCUMENTS:
        print("No valid source documents with chunks were found; nothing to insert.")
        return 0
    if not isinstance(Config.TEI_EMBED_URL, str) or not Config.TEI_EMBED_URL.strip():
        raise ValueError("TEI_EMBED_URL must be present")
    print()
    print("+" + "-" * 78 + "+")
    print("¦" + " " * 78 + "¦")
    print("¦" + "DATA INSERTION SCRIPT".center(78) + "¦")
    print("¦" + " " * 78 + "¦")
    print("+" + "-" * 78 + "+")

    # -- Preview chunk folders before starting ----------------
    preview_chunk_folders(CHUNKS_ROOT_DIR)

    # -- Confirm before proceeding ----------------------------
    print("  Proceed with insertion? (yes/no): ", end="")
    answer = "yes" if yes else input().strip().lower()

    if answer != "yes":
        print("\n  Cancelled.\n")
        return 0

    # -- Connect ----------------------------------------------
    db = Connections()
    try:
        connected = db.connect(insert_only=True) if INSERT_ONLY else db.connect()
    except BaseException:
        db.close()
        raise
    if not connected:
        print("? Connection failed. Exiting.")
        db.close()
        return 1

    try:
        if INSERT_ONLY:
            user_ids, collection_ids = insert_only_preflight(db)
            if preflight_only:
                return 0
        # -- Step 1: Users -------------------------------------
        if not INSERT_ONLY:
            user_ids = insert_users(db.pg)

        # -- Step 2: Collections -------------------------------
        if not INSERT_ONLY:
            collection_ids = insert_collections(db.pg, user_ids)

        # -- Step 3: Documents ? MinIO + PostgreSQL ------------
        document_ids = insert_documents(
            db.pg,
            db.minio,
            user_ids,
            collection_ids
        )
        if len(document_ids) != len(DOCUMENTS):
            raise RuntimeError("Not every discovered datasource was inserted")

        # -- Step 4: Chunks ? PostgreSQL -----------------------
        all_chunk_ids = insert_chunks(db.pg, document_ids)
        if set(all_chunk_ids) != set(document_ids) or any(
            not chunk_ids for chunk_ids in all_chunk_ids.values()
        ):
            raise RuntimeError("Datasource chunk insertion was incomplete")

        # -- Step 5: Embeddings ? Qdrant + PostgreSQL ----------
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

        if INSERT_ONLY:
            verify_insert_only(db, document_ids, all_chunk_ids)

        # -- Step 6: Verify ------------------------------------
        # verify(db.pg, db.qdrant)

        print()
        print("+" + "-" * 78 + "+")
        print("¦" + " " * 78 + "¦")
        print("¦" + "?  ALL DATA INSERTED SUCCESSFULLY".center(78) + "¦")
        print("¦" + " " * 78 + "¦")
        print("+" + "-" * 78 + "+")
        print()
        return 0

    except Exception as e:
        if INSERT_ONLY:
            raise
        print(f"\n? Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        db.close()


class InsertOnlyRefusal(RuntimeError):
    """A fixed, non-sensitive diagnostic safe to display."""


def require_object_absent(minio, key):
    try:
        minio.stat_object(Config.MINIO_BUCKET, key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject"}:
            return
        raise
    raise InsertOnlyRefusal("Object key collision")


def require_vectors_absent(qdrant, ids):
    for offset in range(0, len(ids), 256):
        if qdrant.retrieve(Config.QDRANT_COLLECTION, ids=ids[offset:offset + 256],
                           with_payload=False, with_vectors=False):
            raise InsertOnlyRefusal("Vector ID collision")


def insert_only_preflight(db):
    """Read-only checks; session lock survives insertion commits until close."""
    if len(DOCUMENTS) != 1:
        raise InsertOnlyRefusal("Insert-only requires exactly one source")
    doc = DOCUMENTS[0]
    with db.pg.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))",
                       ("ragbot:add-source:" + doc["title"],))
        cursor.execute("SELECT id FROM documents WHERE title = %s", (doc["title"],))
        if cursor.fetchone():
            raise InsertOnlyRefusal("Document title already exists")
        cursor.execute("SELECT id FROM users WHERE username = %s AND is_active = true",
                       (doc["owner"],))
        owners = cursor.fetchall()
        if len(owners) != 1:
            raise InsertOnlyRefusal("Existing active owner required")
        owner_id = owners[0][0]
        cursor.execute("SELECT id FROM collections WHERE name = %s AND user_id = %s",
                       (doc["collection"], owner_id))
        groups = cursor.fetchall()
        if len(groups) != 1:
            raise InsertOnlyRefusal("Existing owner grouping required")
    if not db.minio.bucket_exists(Config.MINIO_BUCKET):
        raise InsertOnlyRefusal("Existing bucket required")
    info = db.qdrant.get_collection(Config.QDRANT_COLLECTION)
    vectors = info.config.params.vectors
    if (getattr(vectors, "size", None) != Config.QDRANT_VECTOR_SIZE
            or vectors.distance != Distance.COSINE):
        raise InsertOnlyRefusal("Existing vector configuration is incompatible")
    return {doc["owner"]: owner_id}, {doc["collection"]: groups[0][0]}


def verify_insert_only(db, document_ids, all_chunk_ids):
    for title, doc_id in document_ids.items():
        with db.pg.cursor() as cursor:
            cursor.execute("SELECT file_path, file_size FROM documents WHERE id = %s", (doc_id,))
            key, size = cursor.fetchone()
        if db.minio.stat_object(Config.MINIO_BUCKET, key).size != size:
            raise InsertOnlyRefusal("Incomplete object upload")
        expected = len(load_chunks_from_folder(CHUNKS_ROOT_DIR, title))
        ids = all_chunk_ids[title]
        if not expected or len(ids) != expected:
            raise InsertOnlyRefusal("Incomplete chunks")
        with db.pg.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM embeddings WHERE document_id = %s",
                           (doc_id,))
            if cursor.fetchone()[0] != expected:
                raise InsertOnlyRefusal("Incomplete embedding metadata")
            cursor.execute("SELECT processing_status FROM documents WHERE id = %s", (doc_id,))
            if cursor.fetchone()[0] != "completed":
                raise InsertOnlyRefusal("Incomplete document")
        for offset in range(0, len(ids), 256):
            batch = ids[offset:offset + 256]
            points = db.qdrant.retrieve(Config.QDRANT_COLLECTION, ids=batch,
                                       with_payload=True, with_vectors=False)
            if ({point.id for point in points} != set(batch)
                    or any(point.payload.get("document_id") != doc_id for point in points)):
                raise InsertOnlyRefusal("Incomplete vector ingestion")


def main(argv=None):
    global DOCUMENTS, CHUNKS_ROOT_DIR, INSERT_ONLY, SOURCE_NAME
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-name")
    parser.add_argument("--insert-only", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--data-root", default=DATA_DIR)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.data_root:
        parser.error("DATA_INSERTION_DIRECTORY or --data-root is required")
    if (args.insert_only and not args.source_name) or (args.preflight_only and not args.insert_only):
        parser.error("Insert-only requires --source-name; preflight requires --insert-only")
    if args.source_name is not None and (not args.source_name.strip()
                             or args.source_name.startswith(".")
                             or "\\" in args.source_name
                             or Path(args.source_name).name != args.source_name):
        parser.error("Invalid source name")
    INSERT_ONLY, SOURCE_NAME = args.insert_only, args.source_name
    root = Path(args.data_root)
    CHUNKS_ROOT_DIR = str(root / "CHUNKS")
    # Filter before discovery, including before inspecting any unrelated chunks.
    if SOURCE_NAME:
        paths = [p for p in (root / "DOCUMENTS").glob("*")
                 if p.stem == SOURCE_NAME and p.is_file() and p.stat().st_size]
        DOCUMENTS = [{"file_path": str(p), "chunk_dir": SOURCE_NAME,
                      "title": SOURCE_NAME, "owner": "admin", "collection": "Hi_Help"}
                     for p in paths
                     if discover_chunk_files(root / "CHUNKS" / SOURCE_NAME)]
        if len(DOCUMENTS) != 1:
            print("Selected source must have exactly one nonempty document and chunks.")
            return 1
    else:
        DOCUMENTS = [{"file_path": str(s.file_path), "chunk_dir": s.title,
                      "title": s.title, "owner": "admin", "collection": "Hi_Help"}
                     for s in discover_knowledge_sources(root / "DOCUMENTS", root / "CHUNKS")]
    if not INSERT_ONLY:
        return run_import(yes=args.yes)
    if not args.yes and input("Proceed with insert-only operation? (yes/no): ").strip().lower() != "yes":
        return 0
    try:
        # Legacy diagnostics may contain service URLs or chunk read errors.
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            result = run_import(yes=True, preflight_only=args.preflight_only)
        if result:
            raise RuntimeError("Connection failed")
        print("Insert-only preflight passed." if args.preflight_only else "Insert-only ingestion verified.")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        if isinstance(exc, InsertOnlyRefusal):
            print(str(exc))
        print("Insert-only operation failed. Partial NEW data may remain in PostgreSQL, MinIO, "
              "or Qdrant. Nothing was deleted. Inspect state before any retry.")
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\n??  Cancelled\n")
    except Exception as e:
        print(f"\n? Error: {e}\n")
        import traceback

        traceback.print_exc()
