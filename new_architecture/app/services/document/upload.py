# app/services/document/upload.py

"""
Document Upload Service - Minimal Safe Version
===============================================
Handles file uploads to MinIO and database updates
"""

import os
import uuid
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from minio import Minio
from minio.error import S3Error
import psycopg2
import psycopg2.extras

from .validation import DocumentValidator


class DocumentUploadService:
    """Service for uploading documents to MinIO and updating database"""

    def __init__(
            self,
            minio_endpoint: str = "localhost:9000",
            minio_access_key: str = "minioadmin",
            minio_secret_key: str = "minioadmin",
            minio_secure: bool = False,
            minio_bucket: str = "documents",
            db_host: str = "localhost",
            db_port: int = 5432,
            db_name: str = "rag_db",
            db_user: str = "postgres",
            db_password: str = "postgres",
            validator: Optional[DocumentValidator] = None
    ):
        """
        Initialize upload service

        Args:
            minio_endpoint: MinIO endpoint
            minio_access_key: MinIO access key
            minio_secret_key: MinIO secret key
            minio_secure: Use HTTPS
            minio_bucket: MinIO bucket name
            db_host: Database host
            db_port: Database port
            db_name: Database name
            db_user: Database user
            db_password: Database password
            validator: Document validator instance
        """
        # MinIO configuration
        self.minio_endpoint = minio_endpoint
        self.minio_access_key = minio_access_key
        self.minio_secret_key = minio_secret_key
        self.minio_secure = minio_secure
        self.minio_bucket = minio_bucket

        # Database configuration
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password

        # Validator
        self.validator = validator or DocumentValidator()

        # Initialize MinIO client
        self.minio_client = None
        self._init_minio()

    def _init_minio(self):
        """Initialize MinIO client and ensure bucket exists"""
        try:
            self.minio_client = Minio(
                self.minio_endpoint,
                access_key=self.minio_access_key,
                secret_key=self.minio_secret_key,
                secure=self.minio_secure
            )

            # Ensure bucket exists
            if not self.minio_client.bucket_exists(self.minio_bucket):
                self.minio_client.make_bucket(self.minio_bucket)
                print(f"Created MinIO bucket: {self.minio_bucket}")

        except Exception as e:
            print(f"Warning: Failed to initialize MinIO: {e}")
            self.minio_client = None

    def upload_document(
            self,
            file_path: str,
            user_id: int,
            collection_id: Optional[int] = None,
            title: Optional[str] = None,
            meta_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Upload document to MinIO and create database record

        Args:
            file_path: Path to file to upload
            user_id: User ID
            collection_id: Optional collection ID
            title: Optional custom title
            metadata: Optional additional metadata

        Returns:
            Dictionary with upload result
        """
        print()
        print("=" * 80)
        print("DOCUMENT UPLOAD")
        print("=" * 80)
        print()

        # ═══════════════════════════════════════════════════════════
        # STEP 1: VALIDATE FILE
        # ═══════════════════════════════════════════════════════════

        print("→ Step 1: Validating file...")

        is_valid, error = self.validator.validate_file(file_path)
        if not is_valid:
            print(f"  ❌ Validation failed: {error}")
            print()
            return {
                'success': False,
                'error': error
            }

        file_info = self.validator.get_file_info(file_path)

        print(f"  ✓ File is valid")
        print(f"    Filename: {file_info['filename']}")
        print(f"    Size: {file_info['file_size']:,} bytes ({file_info['file_size_mb']} MB)")
        print(f"    Type: {file_info['mime_type']}")
        print()

        # ═══════════════════════════════════════════════════════════
        # STEP 2: CALCULATE FILE HASH
        # ═══════════════════════════════════════════════════════════

        print("→ Step 2: Calculating file hash...")

        file_hash = self._calculate_file_hash(file_path)

        print(f"  ✓ Hash calculated: {file_hash}")
        print()

        # ═══════════════════════════════════════════════════════════
        # STEP 3: GENERATE STORAGE PATH
        # ═══════════════════════════════════════════════════════════

        print("→ Step 3: Generating storage path...")

        doc_uuid = str(uuid.uuid4())
        now = datetime.utcnow()

        filename = file_info['filename']
        file_extension = file_info['file_extension']

        # Storage path format: user_id/year/month/uuid_filename
        minio_path = f"{user_id}/{now.year}/{now.month:02d}/{doc_uuid}_{filename}"

        print(f"  ✓ Storage path: {minio_path}")
        print(f"    UUID: {doc_uuid}")
        print()

        # ═══════════════════════════════════════════════════════════
        # STEP 4: UPLOAD TO MINIO
        # ═══════════════════════════════════════════════════════════

        print("→ Step 4: Uploading to MinIO...")

        if not self.minio_client:
            print(f"  ❌ MinIO client not initialized")
            print()
            return {
                'success': False,
                'error': 'MinIO client not initialized'
            }

        try:
            self.minio_client.fput_object(
                bucket_name=self.minio_bucket,
                object_name=minio_path,
                file_path=file_path,
                content_type=file_info['mime_type']
            )

            print(f"  ✓ Uploaded to MinIO")
            print()

        except S3Error as e:
            print(f"  ❌ MinIO upload failed: {e}")
            print()
            return {
                'success': False,
                'error': f'MinIO upload failed: {e}'
            }

        # ═══════════════════════════════════════════════════════════
        # STEP 5: GENERATE PRESIGNED URL
        # ═══════════════════════════════════════════════════════════

        print("→ Step 5: Generating presigned URL...")

        try:
            presigned_url = self.minio_client.presigned_get_object(
                bucket_name=self.minio_bucket,
                object_name=minio_path,
                expires=timedelta(days=7)
            )

            print(f"  ✓ URL generated (valid for 7 days)")
            print()

        except Exception as e:
            print(f"  ⚠️  URL generation failed: {e}")
            presigned_url = None
            print()

        # ═══════════════════════════════════════════════════════════
        # STEP 6: CREATE DATABASE RECORD
        # ═══════════════════════════════════════════════════════════

        print("→ Step 6: Creating database record...")

        try:
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password
            )

            cursor = conn.cursor()

            # Prepare metadata
            import json
            metadata_json = json.dumps(meta_data or {})

            # Insert document
            cursor.execute("""
                           INSERT INTO documents (uuid, user_id, collection_id, title, filename,
                                                  file_path, file_url, file_size, file_type, mime_type,
                                                  file_hash, status, processing_status,
                                                  meta_data, created_at, updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                           """, (
                               doc_uuid,
                               user_id,
                               collection_id,
                               title or filename,
                               filename,
                               minio_path,
                               presigned_url,
                               file_info['file_size'],
                               self._get_document_type(file_extension),
                               file_info['mime_type'],
                               file_hash,
                               'pending',
                               'pending',
                               metadata_json,
                               now,
                               now
                           ))

            document_id = cursor.fetchone()[0]

            # Update collection stats if collection_id provided
            if collection_id:
                cursor.execute("""
                               UPDATE collections
                               SET document_count = document_count + 1,
                                   total_size     = total_size + %s,
                                   updated_at     = %s
                               WHERE id = %s
                               """, (
                                   file_info['file_size'],
                                   now,
                                   collection_id
                               ))

            conn.commit()

            print(f"  ✓ Database record created")
            print(f"    Document ID: {document_id}")
            print()

            cursor.close()
            conn.close()

        except Exception as e:
            print(f"  ❌ Database error: {e}")
            print()

            # Try to cleanup MinIO upload
            try:
                self.minio_client.remove_object(self.minio_bucket, minio_path)
                print(f"  → Cleaned up MinIO upload")
                print()
            except:
                pass

            return {
                'success': False,
                'error': f'Database error: {e}'
            }

        # ═══════════════════════════════════════════════════════════
        # SUCCESS
        # ═══════════════════════════════════════════════════════════

        print("=" * 80)
        print("✅ UPLOAD SUCCESSFUL")
        print("=" * 80)
        print()

        return {
            'success': True,
            'document_id': document_id,
            'document_uuid': doc_uuid,
            'filename': filename,
            'file_size': file_info['file_size'],
            'file_hash': file_hash,
            'mime_type': file_info['mime_type'],
            'storage_path': minio_path,
            'presigned_url': presigned_url
        }

    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file"""
        sha256_hash = hashlib.sha256()

        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest()

    def _get_document_type(self, file_extension: str) -> str:
        """Get document type from extension"""
        type_map = {
            '.pdf': 'pdf',
            '.txt': 'text',
            '.md': 'markdown',
            '.doc': 'word',
            '.docx': 'word',
            '.csv': 'csv',
            '.xls': 'excel',
            '.xlsx': 'excel',
            '.json': 'json',
            '.xml': 'xml',
            '.html': 'html',
            '.htm': 'html',
            '.rtf': 'text',
            '.odt': 'word',
            '.epub': 'other',
        }

        return type_map.get(file_extension.lower(), 'other')

    def get_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        """
        Get document by ID

        Args:
            document_id: Document ID

        Returns:
            Document dictionary or None
        """
        try:
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password
            )

            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cursor.execute("""
                           SELECT *
                           FROM documents
                           WHERE id = %s
                           """, (document_id,))

            document = cursor.fetchone()

            cursor.close()
            conn.close()

            return dict(document) if document else None

        except Exception as e:
            print(f"Error getting document: {e}")
            return None

    def delete_document(self, document_id: int, user_id: int) -> bool:
        """
        Delete document from MinIO and database

        Args:
            document_id: Document ID
            user_id: User ID (for authorization)

        Returns:
            True if successful
        """
        print()
        print(f"→ Deleting document {document_id}...")

        try:
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password
            )

            cursor = conn.cursor()

            # Get document info
            cursor.execute("""
                           SELECT file_path, user_id, collection_id, file_size
                           FROM documents
                           WHERE id = %s
                           """, (document_id,))

            row = cursor.fetchone()

            if not row:
                print(f"  ❌ Document not found")
                cursor.close()
                conn.close()
                return False

            file_path, doc_user_id, collection_id, file_size = row

            # Check authorization
            if doc_user_id != user_id:
                print(f"  ❌ Unauthorized")
                cursor.close()
                conn.close()
                return False

            # Delete from MinIO
            if self.minio_client:
                try:
                    self.minio_client.remove_object(self.minio_bucket, file_path)
                    print(f"  ✓ Deleted from MinIO")
                except Exception as e:
                    print(f"  ⚠️  MinIO deletion failed: {e}")

            # Delete from database
            cursor.execute("DELETE FROM documents WHERE id = %s", (document_id,))

            # Update collection stats
            if collection_id:
                cursor.execute("""
                               UPDATE collections
                               SET document_count = document_count - 1,
                                   total_size     = total_size - %s,
                                   updated_at     = %s
                               WHERE id = %s
                               """, (
                                   file_size,
                                   datetime.utcnow(),
                                   collection_id
                               ))

            conn.commit()

            print(f"  ✓ Deleted from database")
            print()

            cursor.close()
            conn.close()

            return True

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False