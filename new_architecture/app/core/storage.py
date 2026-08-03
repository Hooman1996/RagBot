# app/core/storage.py

"""
Storage management module
Handles file storage for documents, audio files, and other assets
Supports local filesystem and cloud storage (S3, Azure Blob, GCS)
"""

import logging
import os
import shutil
from typing import Optional, BinaryIO, List, Dict, Any
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import mimetypes
from io import BytesIO
import uuid

from ..config import settings

import os
import io
from pathlib import Path
from typing import Optional, BinaryIO, List, Dict, Any
from datetime import datetime, timedelta
import hashlib
import mimetypes

from minio import Minio
from minio.error import S3Error
from minio.deleteobjects import DeleteObject


from ..utils import logger


logger = logging.getLogger(__name__)


class StorageBackend:
    """
    Base class for storage backends
    """

    def save(self, file_path: str, file_data: BinaryIO, metadata: dict = None) -> str:
        """
        Save file to storage

        Args:
            file_path: Path where file should be saved
            file_data: File data as binary stream
            metadata: Optional metadata dictionary

        Returns:
            Storage path or URL
        """
        raise NotImplementedError

    def load(self, file_path: str) -> bytes:
        """
        Load file from storage

        Args:
            file_path: Path to file

        Returns:
            File data as bytes
        """
        raise NotImplementedError

    def delete(self, file_path: str) -> bool:
        """
        Delete file from storage

        Args:
            file_path: Path to file

        Returns:
            True if successful
        """
        raise NotImplementedError

    def exists(self, file_path: str) -> bool:
        """
        Check if file exists

        Args:
            file_path: Path to file

        Returns:
            True if file exists
        """
        raise NotImplementedError

    def get_url(self, file_path: str, expiration: int = 3600) -> str:
        """
        Get URL for accessing file

        Args:
            file_path: Path to file
            expiration: URL expiration time in seconds

        Returns:
            URL string
        """
        raise NotImplementedError

    def list_files(self, prefix: str = "") -> List[str]:
        """
        List files in storage

        Args:
            prefix: Path prefix to filter files

        Returns:
            List of file paths
        """
        raise NotImplementedError

    def get_metadata(self, file_path: str) -> dict:
        """
        Get file metadata

        Args:
            file_path: Path to file

        Returns:
            Metadata dictionary
        """
        raise NotImplementedError


class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage backend
    """

    def __init__(self, base_path: str):
        """
        Initialize local storage backend

        Args:
            base_path: Base directory for storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Local storage initialized at: {self.base_path}")

    def _get_full_path(self, file_path: str) -> Path:
        """
        Get full filesystem path

        Args:
            file_path: Relative file path

        Returns:
            Full path
        """
        return self.base_path / file_path

    def save(self, file_path: str, file_data: BinaryIO, metadata: dict = None) -> str:
        """
        Save file to local storage

        Args:
            file_path: Path where file should be saved
            file_data: File data as binary stream
            metadata: Optional metadata dictionary

        Returns:
            Storage path
        """
        try:
            full_path = self._get_full_path(file_path)
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            with open(full_path, 'wb') as f:
                shutil.copyfileobj(file_data, f)

            # Save metadata if provided
            if metadata:
                metadata_path = full_path.with_suffix(full_path.suffix + '.meta')
                import json
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f)

            logger.info(f"File saved to local storage: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Error saving file to local storage: {str(e)}")
            raise

    def load(self, file_path: str) -> bytes:
        """
        Load file from local storage

        Args:
            file_path: Path to file

        Returns:
            File data as bytes
        """
        try:
            full_path = self._get_full_path(file_path)
            with open(full_path, 'rb') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading file from local storage: {str(e)}")
            raise

    def delete(self, file_path: str) -> bool:
        """
        Delete file from local storage

        Args:
            file_path: Path to file

        Returns:
            True if successful
        """
        try:
            full_path = self._get_full_path(file_path)

            # Delete file
            if full_path.exists():
                full_path.unlink()

            # Delete metadata if exists
            metadata_path = full_path.with_suffix(full_path.suffix + '.meta')
            if metadata_path.exists():
                metadata_path.unlink()

            logger.info(f"File deleted from local storage: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Error deleting file from local storage: {str(e)}")
            return False

    def exists(self, file_path: str) -> bool:
        """
        Check if file exists in local storage

        Args:
            file_path: Path to file

        Returns:
            True if file exists
        """
        full_path = self._get_full_path(file_path)
        return full_path.exists()

    def get_url(self, file_path: str, expiration: int = 3600) -> str:
        """
        Get URL for accessing file (local path)

        Args:
            file_path: Path to file
            expiration: Not used for local storage

        Returns:
            URL string
        """
        # For local storage, return a file:// URL or relative path
        return f"/storage/{file_path}"

    def list_files(self, prefix: str = "") -> List[str]:
        """
        List files in local storage

        Args:
            prefix: Path prefix to filter files

        Returns:
            List of file paths
        """
        try:
            search_path = self._get_full_path(prefix)
            if search_path.is_file():
                return [prefix]

            files = []
            for file_path in search_path.rglob('*'):
                if file_path.is_file() and not file_path.suffix == '.meta':
                    relative_path = file_path.relative_to(self.base_path)
                    files.append(str(relative_path))

            return files

        except Exception as e:
            logger.error(f"Error listing files in local storage: {str(e)}")
            return []

    def get_metadata(self, file_path: str) -> dict:
        """
        Get file metadata from local storage

        Args:
            file_path: Path to file

        Returns:
            Metadata dictionary
        """
        try:
            full_path = self._get_full_path(file_path)
            metadata_path = full_path.with_suffix(full_path.suffix + '.meta')

            metadata = {}

            # Get file stats
            if full_path.exists():
                stats = full_path.stat()
                metadata.update({
                    'size': stats.st_size,
                    'created_at': datetime.fromtimestamp(stats.st_ctime).isoformat(),
                    'modified_at': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                    'mime_type': mimetypes.guess_type(str(full_path))[0]
                })

            # Load custom metadata if exists
            if metadata_path.exists():
                import json
                with open(metadata_path, 'r') as f:
                    custom_metadata = json.load(f)
                    metadata.update(custom_metadata)

            return metadata

        except Exception as e:
            logger.error(f"Error getting metadata from local storage: {str(e)}")
            return {}


class S3StorageBackend(StorageBackend):
    """
    AWS S3 storage backend
    """

    def __init__(
            self,
            bucket_name: str,
            aws_access_key_id: str = None,
            aws_secret_access_key: str = None,
            region_name: str = None
    ):
        """
        Initialize S3 storage backend

        Args:
            bucket_name: S3 bucket name
            aws_access_key_id: AWS access key ID
            aws_secret_access_key: AWS secret access key
            region_name: AWS region name
        """
        try:
            import boto3

            self.bucket_name = bucket_name

            # Initialize S3 client
            session_kwargs = {}
            if aws_access_key_id:
                session_kwargs['aws_access_key_id'] = aws_access_key_id
            if aws_secret_access_key:
                session_kwargs['aws_secret_access_key'] = aws_secret_access_key
            if region_name:
                session_kwargs['region_name'] = region_name

            self.s3_client = boto3.client('s3', **session_kwargs)

            logger.info(f"S3 storage initialized with bucket: {bucket_name}")

        except ImportError:
            raise ImportError("boto3 is required for S3 storage. Install with: pip install boto3")
        except Exception as e:
            logger.error(f"Error initializing S3 storage: {str(e)}")
            raise

    def save(self, file_path: str, file_data: BinaryIO, metadata: dict = None) -> str:
        """
        Save file to S3

        Args:
            file_path: Path where file should be saved
            file_data: File data as binary stream
            metadata: Optional metadata dictionary

        Returns:
            Storage path
        """
        try:
            extra_args = {}

            # Add metadata
            if metadata:
                extra_args['Metadata'] = {
                    k: str(v) for k, v in metadata.items()
                }

            # Guess content type
            content_type = mimetypes.guess_type(file_path)[0]
            if content_type:
                extra_args['ContentType'] = content_type

            # Upload file
            self.s3_client.upload_fileobj(
                file_data,
                self.bucket_name,
                file_path,
                ExtraArgs=extra_args
            )

            logger.info(f"File saved to S3: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Error saving file to S3: {str(e)}")
            raise

    def load(self, file_path: str) -> bytes:
        """
        Load file from S3

        Args:
            file_path: Path to file

        Returns:
            File data as bytes
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            return response['Body'].read()

        except Exception as e:
            logger.error(f"Error loading file from S3: {str(e)}")
            raise

    def delete(self, file_path: str) -> bool:
        """
        Delete file from S3

        Args:
            file_path: Path to file

        Returns:
            True if successful
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            logger.info(f"File deleted from S3: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Error deleting file from S3: {str(e)}")
            return False

    def exists(self, file_path: str) -> bool:
        """
        Check if file exists in S3

        Args:
            file_path: Path to file

        Returns:
            True if file exists
        """
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            return True
        except:
            return False

    def get_url(self, file_path: str, expiration: int = 3600) -> str:
        """
        Get presigned URL for accessing file

        Args:
            file_path: Path to file
            expiration: URL expiration time in seconds

        Returns:
            Presigned URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': file_path
                },
                ExpiresIn=expiration
            )
            return url

        except Exception as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            raise

    def list_files(self, prefix: str = "") -> List[str]:
        """
        List files in S3

        Args:
            prefix: Path prefix to filter files

        Returns:
            List of file paths
        """
        try:
            files = []
            paginator = self.s3_client.get_paginator('list_objects_v2')

            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        files.append(obj['Key'])

            return files

        except Exception as e:
            logger.error(f"Error listing files in S3: {str(e)}")
            return []

    def get_metadata(self, file_path: str) -> dict:
        """
        Get file metadata from S3

        Args:
            file_path: Path to file

        Returns:
            Metadata dictionary
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=file_path
            )

            metadata = {
                'size': response.get('ContentLength'),
                'content_type': response.get('ContentType'),
                'last_modified': response.get('LastModified').isoformat(),
                'etag': response.get('ETag')
            }

            # Add custom metadata
            if 'Metadata' in response:
                metadata.update(response['Metadata'])

            return metadata

        except Exception as e:
            logger.error(f"Error getting metadata from S3: {str(e)}")
            return {}


class StorageManager:
    """
    Storage manager for handling file operations
    """

    def __init__(self, backend: StorageBackend = None):
        """
        Initialize storage manager

        Args:
            backend: Storage backend to use
        """
        if backend:
            self.backend = backend
        else:
            # Use local storage by default
            storage_path = getattr(settings, 'STORAGE_PATH', './storage')
            self.backend = LocalStorageBackend(storage_path)

        logger.info(f"Storage manager initialized with {type(self.backend).__name__}")

    def save_file(
            self,
            file_data: BinaryIO,
            filename: str,
            category: str = "documents",
            metadata: dict = None
    ) -> Dict[str, Any]:
        """
        Save file to storage

        Args:
            file_data: File data as binary stream
            filename: Original filename
            category: Storage category (documents, audio, images, etc.)
            metadata: Optional metadata

        Returns:
            Dictionary with file information
        """
        try:
            # Generate unique filename
            file_id = str(uuid.uuid4())
            file_extension = Path(filename).suffix
            storage_filename = f"{file_id}{file_extension}"

            # Build storage path
            date_path = datetime.now().strftime("%Y/%m/%d")
            file_path = f"{category}/{date_path}/{storage_filename}"

            # Calculate file hash
            file_data.seek(0)
            file_hash = hashlib.sha256(file_data.read()).hexdigest()
            file_data.seek(0)

            # Prepare metadata
            file_metadata = {
                'original_filename': filename,
                'file_id': file_id,
                'category': category,
                'hash': file_hash,
                'uploaded_at': datetime.utcnow().isoformat()
            }

            if metadata:
                file_metadata.update(metadata)

            # Save file
            storage_path = self.backend.save(file_path, file_data, file_metadata)

            # Get file size
            file_data.seek(0, 2)  # Seek to end
            file_size = file_data.tell()
            file_data.seek(0)  # Reset

            return {
                'file_id': file_id,
                'filename': filename,
                'storage_path': storage_path,
                'size': file_size,
                'hash': file_hash,
                'category': category,
                'uploaded_at': file_metadata['uploaded_at']
            }

        except Exception as e:
            logger.error(f"Error saving file: {str(e)}")
            raise

    def get_file(self, file_path: str) -> bytes:
        """
        Get file from storage

        Args:
            file_path: Path to file

        Returns:
            File data as bytes
        """
        return self.backend.load(file_path)

    def delete_file(self, file_path: str) -> bool:
        """
        Delete file from storage

        Args:
            file_path: Path to file

        Returns:
            True if successful
        """
        return self.backend.delete(file_path)

    def get_file_url(self, file_path: str, expiration: int = 3600) -> str:
        """
        Get URL for accessing file

        Args:
            file_path: Path to file
            expiration: URL expiration time in seconds

        Returns:
            URL string
        """
        return self.backend.get_url(file_path, expiration)

    def file_exists(self, file_path: str) -> bool:
        """
        Check if file exists

        Args:
            file_path: Path to file

        Returns:
            True if file exists
        """
        return self.backend.exists(file_path)

    def list_files(self, category: str = None) -> List[str]:
        """
        List files in storage

        Args:
            category: Optional category filter

        Returns:
            List of file paths
        """
        prefix = f"{category}/" if category else ""
        return self.backend.list_files(prefix)

    def get_file_metadata(self, file_path: str) -> dict:
        """
        Get file metadata

        Args:
            file_path: Path to file

        Returns:
            Metadata dictionary
        """
        return self.backend.get_metadata(file_path)

    def cleanup_old_files(self, days: int = 30, category: str = None) -> int:
        """
        Clean up old files from storage

        Args:
            days: Delete files older than this many days
            category: Optional category filter

        Returns:
            Number of files deleted
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            files = self.list_files(category)
            deleted_count = 0

            for file_path in files:
                metadata = self.get_file_metadata(file_path)

                # Check if file is old enough
                uploaded_at = metadata.get('uploaded_at') or metadata.get('created_at')
                if uploaded_at:
                    file_date = datetime.fromisoformat(uploaded_at.replace('Z', '+00:00'))
                    if file_date < cutoff_date:
                        if self.delete_file(file_path):
                            deleted_count += 1

            logger.info(f"Cleaned up {deleted_count} old files")
            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up old files: {str(e)}")
            return 0


## Hooman : Added MinIOStorage

class MinIOStorage:
    """MinIO object storage manager"""

    def __init__(self):
        """Initialize MinIO client"""
        self.client: Optional[Minio] = None
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self.enabled = settings.MINIO_ENABLED

        if self.enabled:
            self._initialize_client()

    def _initialize_client(self):
        """Initialize MinIO client connection"""
        try:
            self.client = Minio(
                endpoint=f"{settings.MINIO_HOST}:{settings.MINIO_PORT}",
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE
            )

            # Create bucket if it doesn't exist
            self._ensure_bucket_exists()

            logger.info(f"MinIO client initialized - Bucket: {self.bucket_name}")

        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {str(e)}")
            self.enabled = False
            self.client = None

    def _ensure_bucket_exists(self):
        """Ensure the bucket exists, create if not"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created MinIO bucket: {self.bucket_name}")
            else:
                logger.info(f"MinIO bucket exists: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"Error ensuring bucket exists: {str(e)}")
            raise

    def _get_content_type(self, filename: str) -> str:
        """
        Get content type from filename

        Args:
            filename: File name

        Returns:
            MIME type string
        """
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or "application/octet-stream"

    def _calculate_file_hash(self, file_data: bytes) -> str:
        """
        Calculate SHA-256 hash of file

        Args:
            file_data: File bytes

        Returns:
            Hex digest of hash
        """
        return hashlib.sha256(file_data).hexdigest()

    def upload_file(
            self,
            file_data: BinaryIO,
            object_name: str,
            content_type: Optional[str] = None,
            metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Upload file to MinIO

        Args:
            file_data: File-like object or bytes
            object_name: Object name/path in bucket
            content_type: MIME type (auto-detected if None)
            metadata: Additional metadata

        Returns:
            Dictionary with upload information
        """
        if not self.enabled or not self.client:
            raise Exception("MinIO storage is not enabled")

        try:
            # Read file data
            if isinstance(file_data, bytes):
                data = file_data
                file_size = len(data)
                file_stream = io.BytesIO(data)
            else:
                data = file_data.read()
                file_size = len(data)
                file_stream = io.BytesIO(data)

            # Get content type
            if not content_type:
                content_type = self._get_content_type(object_name)

            # Calculate hash
            file_hash = self._calculate_file_hash(data)

            # Prepare metadata
            file_metadata = metadata or {}
            file_metadata['file_hash'] = file_hash
            file_metadata['upload_time'] = datetime.utcnow().isoformat()

            # Upload to MinIO
            result = self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=file_stream,
                length=file_size,
                content_type=content_type,
                metadata=file_metadata
            )

            logger.info(f"Uploaded file to MinIO: {object_name} ({file_size} bytes)")

            return {
                "bucket": self.bucket_name,
                "object_name": object_name,
                "etag": result.etag,
                "version_id": result.version_id,
                "size": file_size,
                "content_type": content_type,
                "file_hash": file_hash,
                "metadata": file_metadata
            }

        except S3Error as e:
            logger.error(f"MinIO upload error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"File upload error: {str(e)}")
            raise

    def download_file(self, object_name: str) -> bytes:
        """
        Download file from MinIO

        Args:
            object_name: Object name/path in bucket

        Returns:
            File data as bytes
        """
        if not self.enabled or not self.client:
            raise Exception("MinIO storage is not enabled")

        try:
            response = self.client.get_object(self.bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()

            logger.info(f"Downloaded file from MinIO: {object_name}")
            return data

        except S3Error as e:
            logger.error(f"MinIO download error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"File download error: {str(e)}")
            raise

    def download_file_stream(self, object_name: str):
        """
        Download file as stream from MinIO

        Args:
            object_name: Object name/path in bucket

        Returns:
            Response object (remember to close it)
        """
        if not self.enabled or not self.client:
            raise Exception("MinIO storage is not enabled")

        try:
            response = self.client.get_object(self.bucket_name, object_name)
            logger.info(f"Streaming file from MinIO: {object_name}")
            return response

        except S3Error as e:
            logger.error(f"MinIO stream error: {str(e)}")
            raise

    def delete_file(self, object_name: str) -> bool:
        """
        Delete file from MinIO

        Args:
            object_name: Object name/path in bucket

        Returns:
            True if successful
        """
        if not self.enabled or not self.client:
            raise Exception("MinIO storage is not enabled")

        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info(f"Deleted file from MinIO: {object_name}")
            return True

        except S3Error as e:
            logger.error(f"MinIO delete error: {str(e)}")
            raise

    def delete_files(self, object_names: List[str]) -> Dict[str, Any]:
        """
        Delete multiple files from MinIO

        Args:
            object_names: List of object names/paths

        Returns:
            Dictionary with deletion results
        """
        if not self.enabled or not self.client:
            raise Exception("MinIO storage is not enabled")

        try:
            delete_objects = [DeleteObject(name) for name in object_names]
            errors = list(self.client.remove_objects(self.bucket_name, delete_objects))

            success_count = len(object_names) - len(errors)

            logger.info(f"Deleted {success_count}/{len(object_names)} files from MinIO")

            return {
                "total": len(object_names),
                "success": success_count,
                "failed": len(errors),
                "errors": [{"object": err.name, "error": str(err)} for err in errors]
            }

        except Exception as e:
            logger.error(f"Batch delete error: {str(e)}")
            raise

    def file_exists(self, object_name: str) -> bool:
        """
        Check if file exists in MinIO

        Args:
            object_name: Object name/path in bucket

        Returns:
            True if exists, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            self.client.stat_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False

    def get_file_info(self, object_name: str) -> Optional[Dict[str, Any]]:
        """
        Get file metadata from MinIO

        Args:
            object_name: Object name/path in bucket

        Returns:
            Dictionary with file information or None
        """
        if not self.enabled or not self.client:
            return None

        try:
            stat = self.client.stat_object(self.bucket_name, object_name)

            return {
                "object_name": object_name,
                "size": stat.size,
                "etag": stat.etag,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "metadata": stat.metadata,
                "version_id": stat.version_id
            }

        except S3Error as e:
            logger.error(f"Error getting file info: {str(e)}")
            return None

    def list_files(
            self,
            prefix: Optional[str] = None,
            recursive: bool = True,
            max_results: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        List files in MinIO bucket

        Args:
            prefix: Filter by prefix
            recursive: List recursively
            max_results: Maximum number of results

        Returns:
            List of file information dictionaries
        """
        if not self.enabled or not self.client:
            return []

        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=prefix,
                recursive=recursive
            )

            files = []
            for obj in objects:
                files.append({
                    "object_name": obj.object_name,
                    "size": obj.size,
                    "etag": obj.etag,
                    "last_modified": obj.last_modified,
                    "content_type": obj.content_type,
                    "is_dir": obj.is_dir,
                    "metadata": obj.meta_data
                })

                if max_results and len(files) >= max_results:
                    break

            logger.info(f"Listed {len(files)} files from MinIO")
            return files

        except S3Error as e:
            logger.error(f"Error listing files: {str(e)}")
            return []

    def get_presigned_url(
            self,
            object_name: str,
            expires: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate presigned URL for file access

        Args:
            object_name: Object name/path in bucket
            expires: URL expiration time

        Returns:
            Presigned URL string
        """
        if not self.enabled or not self.client:
            raise Exception("MinIO storage is not enabled")

        try:
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_name,
                expires=expires
            )

            logger.info(f"Generated presigned URL for: {object_name}")
            return url

        except S3Error as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            raise

    def get_presigned_upload_url(
            self,
            object_name: str,
            expires: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate presigned URL for file upload

        Args:
            object_name: Object name/path in bucket
            expires: URL expiration time

        Returns:
            Presigned upload URL string
        """
        if not self.enabled or not self.client:
            raise Exception("MinIO storage is not enabled")

        try:
            url = self.client.presigned_put_object(
                self.bucket_name,
                object_name,
                expires=expires
            )

            logger.info(f"Generated presigned upload URL for: {object_name}")
            return url

        except S3Error as e:
            logger.error(f"Error generating presigned upload URL: {str(e)}")
            raise

    def copy_file(
            self,
            source_object: str,
            dest_object: str
    ) -> Dict[str, Any]:
        """
        Copy file within MinIO

        Args:
            source_object: Source object name
            dest_object: Destination object name

        Returns:
            Dictionary with copy information
        """
        if not self.enabled or not self.client:
            raise Exception("MinIO storage is not enabled")

        try:
            from minio.commonconfig import CopySource

            result = self.client.copy_object(
                self.bucket_name,
                dest_object,
                CopySource(self.bucket_name, source_object)
            )

            logger.info(f"Copied file: {source_object} -> {dest_object}")

            return {
                "source": source_object,
                "destination": dest_object,
                "etag": result.etag,
                "version_id": result.version_id
            }

        except S3Error as e:
            logger.error(f"Error copying file: {str(e)}")
            raise

    def get_bucket_stats(self) -> Dict[str, Any]:
        """
        Get bucket statistics

        Returns:
            Dictionary with bucket statistics
        """
        if not self.enabled or not self.client:
            return {"enabled": False}

        try:
            objects = self.client.list_objects(self.bucket_name, recursive=True)

            total_size = 0
            total_files = 0

            for obj in objects:
                total_files += 1
                total_size += obj.size

            return {
                "enabled": True,
                "bucket": self.bucket_name,
                "total_files": total_files,
                "total_size": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2)
            }

        except S3Error as e:
            logger.error(f"Error getting bucket stats: {str(e)}")
            return {"enabled": True, "error": str(e)}


# Create global storage instance
storage = MinIOStorage()


# Helper functions for common operations
async def upload_document(
        file_data: BinaryIO,
        user_id: int,
        filename: str,
        metadata: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Upload document file

    Args:
        file_data: File data
        user_id: User ID
        filename: Original filename
        metadata: Additional metadata

    Returns:
        Upload information
    """
    # Generate object name with user folder structure
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_filename = filename.replace(" ", "_").replace("/", "_")
    object_name = f"documents/{user_id}/{timestamp}_{safe_filename}"

    # Add user info to metadata
    file_metadata = metadata or {}
    file_metadata['user_id'] = str(user_id)
    file_metadata['original_filename'] = filename

    return storage.upload_file(file_data, object_name, metadata=file_metadata)


async def download_document(object_name: str) -> bytes:
    """
    Download document file

    Args:
        object_name: Object name in storage

    Returns:
        File data
    """
    return storage.download_file(object_name)


async def delete_document(object_name: str) -> bool:
    """
    Delete document file

    Args:
        object_name: Object name in storage

    Returns:
        True if successful
    """
    return storage.delete_file(object_name)


async def get_download_url(
        object_name: str,
        expires_minutes: int = 60
) -> str:
    """
    Get presigned download URL

    Args:
        object_name: Object name in storage
        expires_minutes: URL expiration in minutes

    Returns:
        Presigned URL
    """
    return storage.get_presigned_url(
        object_name,
        expires=timedelta(minutes=expires_minutes)
    )





# Global storage manager instance
storage_manager = StorageManager()


def get_storage() -> StorageManager:
    """
    Get storage manager instance

    Returns:
        StorageManager instance
    """
    return storage_manager