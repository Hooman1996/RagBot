# app/services/document/validation.py

"""
Document Validation Service - Minimal Safe Version
===================================================
Validates files before upload
"""

import os
import mimetypes
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

# Try to import magic, fallback if not available
try:
    import magic

    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False


class DocumentValidator:
    """Validates documents before upload"""

    # Maximum file sizes by type (in bytes)
    MAX_FILE_SIZES = {
        "pdf": 100 * 1024 * 1024,  # 100 MB
        "txt": 10 * 1024 * 1024,  # 10 MB
        "md": 10 * 1024 * 1024,  # 10 MB
        "doc": 50 * 1024 * 1024,  # 50 MB
        "docx": 50 * 1024 * 1024,  # 50 MB
        "csv": 50 * 1024 * 1024,  # 50 MB
        "xlsx": 50 * 1024 * 1024,  # 50 MB
        "xls": 50 * 1024 * 1024,  # 50 MB
        "json": 10 * 1024 * 1024,  # 10 MB
        "xml": 10 * 1024 * 1024,  # 10 MB
        "html": 10 * 1024 * 1024,  # 10 MB
        "htm": 10 * 1024 * 1024,  # 10 MB
        "rtf": 20 * 1024 * 1024,  # 20 MB
        "odt": 50 * 1024 * 1024,  # 50 MB
        "epub": 50 * 1024 * 1024,  # 50 MB
        "default": 100 * 1024 * 1024  # 100 MB
    }

    # Allowed MIME types
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/html",
        "text/xml",
        "application/json",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/rtf",
        "application/epub+zip",
        "application/vnd.oasis.opendocument.text",
    }

    # Allowed file extensions
    ALLOWED_EXTENSIONS = {
        ".pdf", ".txt", ".md", ".csv", ".html", ".htm", ".xml", ".json",
        ".doc", ".docx", ".xls", ".xlsx", ".rtf", ".odt", ".epub"
    }

    def __init__(
            self,
            max_file_size: Optional[int] = None,
            allowed_extensions: Optional[set] = None,
            allowed_mime_types: Optional[set] = None
    ):
        """
        Initialize validator

        Args:
            max_file_size: Maximum file size in bytes (overrides defaults)
            allowed_extensions: Set of allowed extensions (overrides defaults)
            allowed_mime_types: Set of allowed MIME types (overrides defaults)
        """
        self.max_file_size = max_file_size
        self.allowed_extensions = allowed_extensions or self.ALLOWED_EXTENSIONS
        self.allowed_mime_types = allowed_mime_types or self.ALLOWED_MIME_TYPES

    def validate_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a file

        Args:
            file_path: Path to file

        Returns:
            Tuple of (is_valid, error_message)
        """
        path = Path(file_path)

        # Check if file exists
        if not path.exists():
            return False, f"File not found: {file_path}"

        # Check if it's a file
        if not path.is_file():
            return False, f"Not a file: {file_path}"

        # Check file extension
        file_extension = path.suffix.lower()
        if file_extension not in self.allowed_extensions:
            return False, (
                f"File type '{file_extension}' not allowed. "
                f"Allowed types: {', '.join(sorted(self.allowed_extensions))}"
            )

        # Check file size
        file_size = path.stat().st_size

        if file_size == 0:
            return False, "File is empty"

        # Get max size for this file type
        max_size = self.max_file_size or self.MAX_FILE_SIZES.get(
            file_extension.lstrip('.'),
            self.MAX_FILE_SIZES["default"]
        )

        if file_size > max_size:
            return False, (
                f"File size ({file_size / 1024 / 1024:.2f} MB) exceeds "
                f"maximum allowed size ({max_size / 1024 / 1024:.2f} MB)"
            )

        # Validate MIME type
        is_valid, error = self.validate_mime_type(file_path)
        if not is_valid:
            return False, error

        return True, None

    def validate_mime_type(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate MIME type of file

        Args:
            file_path: Path to file

        Returns:
            Tuple of (is_valid, error_message)
        """
        mime_type = self.detect_mime_type(file_path)

        if mime_type not in self.allowed_mime_types:
            # Check if it's a text file variant
            if mime_type.startswith('text/'):
                return True, None

            return False, (
                f"MIME type '{mime_type}' not allowed. "
                f"File may be corrupted or of unsupported type."
            )

        return True, None

    def detect_mime_type(self, file_path: str) -> str:
        """
        Detect MIME type of file

        Args:
            file_path: Path to file

        Returns:
            MIME type string
        """
        if HAS_MAGIC:
            try:
                mime = magic.Magic(mime=True)
                return mime.from_file(file_path)
            except Exception:
                pass

        # Fallback to mimetypes module
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Get file information

        Args:
            file_path: Path to file

        Returns:
            Dictionary with file information
        """
        path = Path(file_path)

        if not path.exists():
            return {}

        stats = path.stat()

        return {
            'filename': path.name,
            'file_extension': path.suffix.lower(),
            'file_size': stats.st_size,
            'file_size_mb': round(stats.st_size / (1024 * 1024), 2),
            'mime_type': self.detect_mime_type(file_path),
            'created_at': stats.st_ctime,
            'modified_at': stats.st_mtime,
        }