# app/__init__.py

"""
Banking RAG System
Advanced Retrieval-Augmented Generation system for banking documents
with OCR, voice processing, PDF viewing, and feedback collection.
"""

__version__ = "1.0.0"
__author__ = "Banking RAG Team"
__description__ = "Advanced RAG System for Banking Documents"

from .config import Config

# Package metadata
__all__ = [
    "__version__",
    "__author__",
    "__description__",
    "Config",
]